import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import HttpUrl, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Stored as a comma-separated string to avoid pydantic-settings JSON-decoding
    # list fields before validators can run. Parse with .allowed_host_list.
    model_config = SettingsConfigDict(env_prefix="")

    allowed_hosts: str = ""

    @property
    def allowed_host_list(self) -> list[str]:
        if not self.allowed_hosts:
            return []
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]


@dataclass(frozen=True, slots=True)
class CachedResponse:
    body: bytes
    content_type: str
    status_code: int


settings = Settings()
cache: dict[str, CachedResponse] = {}
lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        app.state.client = client
        yield


app = FastAPI(title="cacher", lifespan=lifespan)


def validate_url(url: str) -> str:
    try:
        parsed = HttpUrl(url)
    except ValidationError:
        raise HTTPException(status_code=422, detail=f"Invalid URL: {url}")
    host = parsed.host
    allowed = settings.allowed_host_list
    if allowed and host not in allowed:
        raise HTTPException(status_code=403, detail=f"Host not allowed: {host}")
    return str(parsed)


async def fetch_url(client: httpx.AsyncClient, url: str) -> CachedResponse:
    response = await client.get(url, follow_redirects=True)
    return CachedResponse(
        body=response.content,
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


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/get")
async def get_cached(url: str = Query(...)):
    url = validate_url(url)

    if url in cache:
        return make_response(cache[url], "hit")

    async with lock:
        if url in cache:
            return make_response(cache[url], "hit")
        cached = await fetch_url(app.state.client, url)
        cache[url] = cached

    return make_response(cached, "miss")


@app.post("/refresh")
async def refresh(url: str = Query(...)):
    url = validate_url(url)

    async with lock:
        cached = await fetch_url(app.state.client, url)
        cache[url] = cached

    return make_response(cached, "refresh")


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)
