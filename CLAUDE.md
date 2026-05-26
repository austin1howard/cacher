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

Modules under `src/cacher/`:

- `runtime_settings.py` — `Settings` (pydantic-settings, reads `ALLOWED_HOSTS`), `CachedResponse` frozen dataclass, module-level `cache` dict and asyncio `lock`
- `api.py` — `lifespan`, `app`, `validate_url()`, `fetch_url()`, `make_response()`, route handlers, `main()`
- `__init__.py` — re-exports `app` and `main` so `cacher:app` works

## FastAPI conventions

- Use `Annotated` for query/path parameters — `url: Annotated[str, Query()]` — not `Query(...)` as the default value. See [FastAPI docs](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#annotated-as-the-type).
- Use `AfterValidator` (from pydantic) for custom parameter validation instead of calling a validation function manually in the route body. Validators raise `ValueError`; define a named type alias (e.g. `ValidatedUrl`) and reuse it across routes. See [FastAPI docs](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#custom-validation).

## Key env vars

| Var | Purpose |
|---|---|
| `ALLOWED_HOSTS` | Comma-separated hostnames allowed as upstream targets |
