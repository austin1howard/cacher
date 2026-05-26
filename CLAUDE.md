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
CACHER_ALLOWED_HOSTS='["httpbin.org"]' uv run cacher
# or
uvicorn cacher:app --reload
```

Server runs on `http://0.0.0.0:8000`.

## Testing

Run the test suite:

```bash
uv run pytest -v
```

Tests live in `tests/` and use `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`). A dummy FastAPI app served via `httpx.ASGITransport` acts as the upstream — no real network calls. The `client` fixture in `conftest.py` wires everything together.

Smoke-test against a live server:

```bash
curl http://localhost:8000/healthz
curl -i "http://localhost:8000/get?url=https://httpbin.org/get"
curl -i -X POST "http://localhost:8000/refresh?url=https://httpbin.org/get"
```

## Architecture

Modules under `src/cacher/`:

- `runtime_settings.py` — `Settings` (pydantic-settings, reads `CACHER_ALLOWED_HOSTS`)
- `api.py` — `CachedResponse`, module-level `cache` dict and asyncio `lock`, `lifespan`, `app`, `validate_url()`, `fetch_url()`, `make_response()`, route handlers, `main()`
- `__init__.py` — re-exports `app` and `main` so `cacher:app` works

## Python conventions

- Use pydantic `BaseModel` for data classes, not `dataclass`. Use `model_config = {"frozen": True}` for immutable models.

## FastAPI conventions

- Use `Annotated` for query/path parameters — `url: Annotated[str, Query()]` — not `Query(...)` as the default value. See [FastAPI docs](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#annotated-as-the-type).
- Use `AfterValidator` (from pydantic) for custom parameter validation instead of calling a validation function manually in the route body. Validators raise `ValueError`; define a named type alias (e.g. `ValidatedUrl`) and reuse it across routes. See [FastAPI docs](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#custom-validation).

## Linting and formatting
This project uses Ruff for both linting and formatting. Do not call Black,
flake8, isort, or pylint.
- Lint: `uv run ruff check .`
- Lint and auto-fix: `uv run ruff check --fix .`
- Format: `uv run ruff format .`
- Check formatting without writing: `uv run ruff format --check .`
- Always invoke Ruff through `uv run` so it resolves to the project's
  virtual environment.
Ruff configuration lives in `pyproject.toml` under `[tool.ruff]`. Do not
add a separate `ruff.toml` or `.ruff.toml`. Do not add inline `# noqa`
comments without a rule code.


## Key env vars

| Var | Purpose |
|---|---|
| `CACHER_ALLOWED_HOSTS` | JSON list of hostnames allowed as upstream targets (e.g. `["httpbin.org"]`) |
