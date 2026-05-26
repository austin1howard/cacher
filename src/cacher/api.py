from contextlib import asynccontextmanager
from typing import Annotated

import httpx
import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import Response
from pydantic import AfterValidator, HttpUrl, ValidationError

from cacher.runtime_settings import CachedResponse, cache, lock, settings


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
        raise ValueError(f"Invalid URL: {url}")
    host = parsed.host
    allowed = settings.allowed_host_list
    if allowed and host not in allowed:
        raise ValueError(f"Host not allowed: {host}")
    return str(parsed)


ValidatedUrl = Annotated[str, Query(), AfterValidator(validate_url)]


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
async def get_cached(url: ValidatedUrl):
    if url in cache:
        return make_response(cache[url], "hit")

    async with lock:
        if url in cache:
            return make_response(cache[url], "hit")
        cached = await fetch_url(app.state.client, url)
        cache[url] = cached

    return make_response(cached, "miss")


@app.post("/refresh")
async def refresh(url: ValidatedUrl):
    async with lock:
        cached = await fetch_url(app.state.client, url)
        cache[url] = cached

    return make_response(cached, "refresh")


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)
