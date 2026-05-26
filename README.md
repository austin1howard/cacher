# cacher

Lightweight HTTP caching proxy with manual cache-busting. Fetches and stores remote HTTP responses in-memory, serving cached content on subsequent requests. Supports an allowlist of permitted upstream hosts.

## Quick start

```bash
uv sync
CACHER_ALLOWED_HOSTS='["httpbin.org"]' uv run cacher
```

The server starts on `http://0.0.0.0:8000`.

## Configuration

| Environment variable | Description | Example |
|---|---|---|
| `CACHER_ALLOWED_HOSTS` | JSON list of permitted upstream hostnames. If unset, all hosts are allowed. | `'["httpbin.org","api.example.com"]'` |

## Endpoints

### `GET /healthz`

Health check.

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

### `GET /get?url=<url>`

Return the cached response for a URL. On the first request the upstream is fetched and the response is cached. Subsequent requests are served from cache.

The `X-Cache` response header indicates `hit` (served from cache) or `miss` (fetched from upstream).

```bash
curl -i "http://localhost:8000/get?url=https://httpbin.org/get"
# X-Cache: miss  (first request)

curl -i "http://localhost:8000/get?url=https://httpbin.org/get"
# X-Cache: hit   (subsequent requests)
```

### `POST /refresh?url=<url>`

Force a re-fetch of the URL and update the cache. Returns the fresh response with `X-Cache: refresh`.

```bash
curl -i -X POST "http://localhost:8000/refresh?url=https://httpbin.org/get"
# X-Cache: refresh
```

## Running without the CLI

```bash
uvicorn cacher:app --reload
```
