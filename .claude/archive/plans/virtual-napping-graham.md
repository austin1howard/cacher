# Plan: Implement Cacher — Lightweight Caching Proxy

## Context

The `cacher` package is scaffolded but has no implementation yet. The goal is to build a FastAPI caching proxy that fetches and caches HTTP responses in-memory, with manual cache-busting via a `/refresh` endpoint. This serves as a lightweight layer to reduce redundant external HTTP calls.

## Files to modify

| File | Action |
|---|---|
| `pyproject.toml` | Add `httpx` dependency |
| `src/cacher/__init__.py` | Full implementation (replace placeholder) |
| `README.md` | Project docs |
| `CLAUDE.md` | New — dev guide |

## Implementation: `src/cacher/__init__.py`

Single-module design (~120 lines). Components in order:

### Settings
- `Settings(BaseSettings)` with `allowed_hosts: list[str] = []`
- `@field_validator("allowed_hosts", mode="before")` to parse comma-separated env var `ALLOWED_HOSTS="host1.com,host2.com"`
- Empty list = all hosts allowed

### Cache data
- `CachedResponse` dataclass (frozen, slots): `body: bytes`, `content_type: str`, `status_code: int`
- Module-level `cache: dict[str, CachedResponse]` and `lock = asyncio.Lock()`

### Lifespan
- Create `httpx.AsyncClient` in lifespan context manager, store on `app.state.client`

### URL validation helper
- `validate_url(url: str) -> str` — validate with `HttpUrl(url)`, check `parsed.host` against `settings.allowed_hosts`, raise 403 if not allowed

### Fetch helper
- `fetch_url(client, url) -> CachedResponse` — `client.get(url, follow_redirects=True)`

### Response builder
- `make_response(cached, cache_header) -> Response` — returns raw proxied body with original content-type and `X-Cache` header

### Endpoints
1. **`GET /healthz`** — returns `{"status": "ok"}`
2. **`GET /get?url=<url>`** — check cache → lock → recheck → fetch if miss. `X-Cache: hit` or `miss`
3. **`POST /refresh?url=<url>`** — lock → fetch → update cache. `X-Cache: refresh`

### Entrypoint
- `main()` calls `uvicorn.run(app, host="0.0.0.0", port=8000)`

## pyproject.toml change

Add `"httpx>=0.28.0"` to dependencies, then `uv lock && uv sync`.

## README.md

Brief project description, quick start (`uv sync && uv run cacher`), env vars, endpoint docs with curl examples.

## CLAUDE.md

Package manager (`uv`), run/test commands, architecture note (single module), key env var.

## Verification

1. `uv lock && uv sync` — deps resolve
2. `ALLOWED_HOSTS="httpbin.org" uv run cacher` — starts on port 8000
3. `curl localhost:8000/healthz` — `{"status":"ok"}`
4. `curl "localhost:8000/get?url=https://httpbin.org/get"` — proxied response, `X-Cache: miss`
5. Same curl again — `X-Cache: hit`
6. `curl -X POST "localhost:8000/refresh?url=https://httpbin.org/get"` — `X-Cache: refresh`
7. `curl "localhost:8000/get?url=https://example.com/foo"` — 403 (host not allowed)
