# Add Unit Tests for Cacher

## Context

The cacher project has no test suite. We need comprehensive pytest tests covering happy paths, failure paths, and concurrency/race conditions. pytest and pytest-asyncio are already in dev dependencies. Tests should use a local in-process dummy HTTP server to avoid internet dependency.

## Configuration

**`pyproject.toml`** — add pytest-asyncio auto mode:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

## File Structure

```
tests/
  conftest.py
  test_healthz.py
  test_validation.py
  test_get.py
  test_refresh.py
  test_concurrency.py
```

## Fixture Design (`tests/conftest.py`)

### Dummy upstream app

A small FastAPI app acting as the upstream server, served via `httpx.ASGITransport` (no real network):

- `GET /payload` — returns `{"msg": "hello"}` with JSON content-type
- `GET /slow` — sleeps 0.2s then returns (forces lock contention)
- `GET /counter` — increments + returns an integer counter (verifies fetch count)
- `GET /error` — returns 500
- `GET /text` — returns plain text with `text/plain` content-type

### Key fixtures

- **`_clear_cache`** (autouse, function-scoped) — calls `cacher.api.cache.clear()` before each test
- **`_reset_counter`** (autouse, function-scoped) — resets the dummy counter to 0
- **`client`** — creates `httpx.AsyncClient(transport=ASGITransport(app=app))` as the test client, and wires `app.state.client` to point at the dummy upstream via its own `ASGITransport`. No real lifespan needed — we set `app.state.client` directly.

### Why ASGITransport + AsyncClient (not TestClient)

`TestClient` is synchronous and runs the app in a separate thread, which means `asyncio.Lock` won't provide real mutual exclusion for concurrency tests. Using `httpx.AsyncClient` with `ASGITransport` keeps everything on one event loop so `asyncio.gather` produces genuine coroutine interleaving.

### URL scheme

Test URLs will be `http://localhost/payload`, `http://localhost/counter`, etc. Since `allowed_hosts` defaults to `[]` (allow all), no settings override needed for most tests. Only validation tests monkeypatch `settings.allowed_hosts`.

## Test Cases

### `test_healthz.py`
1. `test_healthz` — GET /healthz → 200, `{"status": "ok"}`

### `test_validation.py` (unit tests for `validate_url` + HTTP-level 422s)
2. `test_valid_url` — `validate_url("http://example.com/foo")` returns normalized string
3. `test_invalid_url_raises` — `validate_url("not-a-url")` raises `ValueError`
4. `test_disallowed_host` — monkeypatch `allowed_hosts=["allowed.com"]`, call with `http://blocked.com/x` → `ValueError`
5. `test_allowed_host_passes` — monkeypatch `allowed_hosts=["example.com"]`, succeeds
6. `test_empty_allowed_hosts_permits_all` — default `[]` allows any host
7. `test_get_invalid_url_422` — GET `/get?url=not-a-url` → 422
8. `test_get_disallowed_host_422` — monkeypatch, GET with blocked host → 422

### `test_get.py` (happy + failure paths for GET /get)
9. `test_cache_miss` — first GET returns upstream body, `X-Cache: miss`
10. `test_cache_hit` — second GET same URL → `X-Cache: hit`, same body
11. `test_different_urls_independent` — GET url_a, GET url_b → both miss
12. `test_upstream_error_proxied` — GET url returning 500 → status 500 proxied
13. `test_content_type_preserved` — upstream `text/plain` → response has `text/plain`
14. `test_slow_endpoint_cached` — GET `/get?url=.../slow` (sleeps 0.2s upstream), assert `X-Cache: miss` and measure wall time. Second GET same URL → `X-Cache: hit` and completes significantly faster (near-instant, no upstream delay).

### `test_refresh.py`
15. `test_refresh_returns_refresh_header` — POST /refresh → `X-Cache: refresh`
16. `test_refresh_updates_cache` — GET (counter=1, miss), then multiple GETs all returning counter=1 (hit, proving cache is stable). Then refresh (counter=2). Then multiple GETs all returning counter=2 (hit, proving refresh updated the cached value).
17. `test_refresh_populates_empty_cache` — refresh on uncached URL works, subsequent GET is hit

### `test_concurrency.py` (race conditions via `asyncio.gather`)
18. `test_concurrent_gets_single_fetch` — fire 10 concurrent GETs to `/counter`. Assert only 1 upstream fetch occurred (counter=1 in all responses). Validates double-checked locking.
19. `test_concurrent_gets_different_urls` — concurrent GETs to different URLs → all miss (lock serializes but doesn't prevent fetching different URLs)
20. `test_get_and_refresh_interleaved` — seed cache with GET (counter=1). Fire concurrent GET + refresh. After both, final GET returns refreshed value (counter=2).
21. `test_multiple_concurrent_refreshes` — fire 5 concurrent refreshes to `/counter`. All return `X-Cache: refresh`. Counter values should be sequential (1,2,3,4,5) since they serialize through the lock.

## Files to Modify

| File | Action |
|------|--------|
| `pyproject.toml` | Add `[tool.pytest.ini_options]` section |
| `tests/conftest.py` | Create — fixtures + dummy app |
| `tests/test_healthz.py` | Create |
| `tests/test_validation.py` | Create |
| `tests/test_get.py` | Create |
| `tests/test_refresh.py` | Create |
| `tests/test_concurrency.py` | Create |

## Verification

```bash
uv run pytest -v
uv run ruff check tests/
uv run ruff format --check tests/
```
