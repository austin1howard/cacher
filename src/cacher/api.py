import asyncio
import ipaddress
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import AfterValidator, BaseModel, HttpUrl, ValidationError

from cacher.runtime_settings import settings

_ALLOWED_PORTS = {None, 80, 443}

# Literal IP ranges that must never be reached (SSRF defense-in-depth)
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]
# Well-known hostnames that resolve to loopback (string check, defense-in-depth)
_BLOCKED_HOSTNAMES = frozenset({"localhost", "0.0.0.0"})


class CachedResponse(BaseModel):
    model_config = {"frozen": True}

    body: bytes
    content_type: str
    status_code: int


cache: dict[str, CachedResponse] = {}
# Per-URL locks prevent a global lock from serialising all cache misses.
_url_locks: dict[str, asyncio.Lock] = {}
_url_locks_meta = asyncio.Lock()  # guards _url_locks dict itself


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=10.0) as client:
        app.state.client = client
        yield


# Disable docs endpoints — they expose the full API schema
app = FastAPI(
    title="cacher",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_blocked_ip(host: str) -> bool:
    """Return True if *host* is a literal IP address inside a blocked network."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False  # not a literal IP — hostname, validated separately
    return any(addr in net for net in _BLOCKED_NETWORKS)


def validate_url(url: str) -> str:
    try:
        parsed = HttpUrl(url)
    except ValidationError:
        raise ValueError(f"Invalid URL: {url}")

    host = parsed.host

    allowed = settings.allowed_hosts
    if host not in allowed:
        raise ValueError(f"Host not allowed: {host}")

    # Block well-known loopback hostnames (defense-in-depth)
    if host in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Host not allowed: {host}")

    # Block literal private / internal IP addresses
    if _is_blocked_ip(host):
        raise ValueError(f"Host not allowed: {host}")

    # Restrict to standard web ports only (None means default for the scheme)
    if parsed.port not in _ALLOWED_PORTS:
        raise ValueError(f"Port not allowed: {parsed.port}")

    return str(parsed)


ValidatedUrl = Annotated[str, Query(), AfterValidator(validate_url)]


async def _get_url_lock(url: str) -> asyncio.Lock:
    if url in _url_locks:
        return _url_locks[url]
    else:
        async with _url_locks_meta:
            if url not in _url_locks:
                _url_locks[url] = asyncio.Lock()
            return _url_locks[url]


async def fetch_url(client: httpx.AsyncClient, url: str) -> CachedResponse:
    # follow_redirects=False: redirects could bypass host validation by
    # pointing at a private/internal address on an allowed domain.
    try:
        async with client.stream("GET", url, follow_redirects=False) as response:
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > settings.max_response_body_bytes:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Upstream response exceeds {settings.max_response_body_bytes} bytes",
                    )
                chunks.append(chunk)
            body = b"".join(chunks)
    except httpx.TransportError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream unreachable: {exc}") from exc
    return CachedResponse(
        body=body,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        status_code=response.status_code,
    )


def make_response(cached: CachedResponse, cache_header: str) -> Response:
    return Response(
        content=cached.body,
        media_type=cached.content_type,
        status_code=cached.status_code,
        headers={"X-Cache": cache_header},
    )


def _evict_if_full() -> None:
    """FIFO eviction: drop the oldest entry when the cache is at capacity."""
    while len(cache) >= settings.max_cache_entries:
        oldest = next(iter(cache))
        del cache[oldest]
        _url_locks.pop(oldest, None)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/get")
async def get_cached(url: ValidatedUrl):
    if url in cache:
        return make_response(cache[url], "hit")

    url_lock = await _get_url_lock(url)
    async with url_lock:
        if url in cache:
            return make_response(cache[url], "hit")
        fetched = await fetch_url(app.state.client, url)
        # Don't cache 5xx responses — they represent transient upstream failures.
        if fetched.status_code < 500:
            _evict_if_full()
            cache[url] = fetched

    return make_response(fetched, "miss")


@app.post("/refresh")
async def refresh(url: ValidatedUrl):
    url_lock = await _get_url_lock(url)
    async with url_lock:
        fetched = await fetch_url(app.state.client, url)
        if fetched.status_code < 500:
            _evict_if_full()
            cache[url] = fetched

    return make_response(fetched, "refresh")


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)
