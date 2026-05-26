# CLAUDE.md

## Project

`cacher` — lightweight FastAPI caching proxy. Single-module app at `src/cacher/__init__.py`.

## Package manager

This project uses `uv`. Do not use `pip` directly.

```bash
uv sync           # install dependencies
uv add <package>  # add a dependency
uv lock           # regenerate lockfile
```

## Running

```bash
ALLOWED_HOSTS="httpbin.org" uv run cacher
# or
uvicorn cacher:app --reload
```

Server runs on `http://0.0.0.0:8000`.

## Testing

No test suite yet. Smoke-test with:

```bash
curl http://localhost:8000/healthz
curl -i "http://localhost:8000/get?url=https://httpbin.org/get"
curl -i -X POST "http://localhost:8000/refresh?url=https://httpbin.org/get"
```

## Architecture

All logic lives in `src/cacher/__init__.py`:

- `Settings` — pydantic-settings class; reads `ALLOWED_HOSTS` env var (comma-separated)
- `CachedResponse` — frozen dataclass holding `body`, `content_type`, `status_code`
- `cache` / `lock` — module-level in-memory store and asyncio lock
- `lifespan` — manages `httpx.AsyncClient` lifecycle; stored on `app.state.client`
- `validate_url()` — validates URL format and host allowlist
- `fetch_url()` — async GET via httpx
- `make_response()` — builds FastAPI `Response` with `X-Cache` header
- `main()` — entrypoint, runs `uvicorn.run(app)`

## Key env vars

| Var | Purpose |
|---|---|
| `ALLOWED_HOSTS` | Comma-separated hostnames allowed as upstream targets |
