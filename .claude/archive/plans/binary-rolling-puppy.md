# Security Vulnerability Review — cacher

## Context

`cacher` is a FastAPI caching proxy that accepts a user-supplied URL, fetches it via httpx, caches the response in-memory, and returns it. This architecture is inherently high-risk — it's an open proxy pattern where SSRF is the primary threat model. This review covers `src/cacher/api.py`, `src/cacher/runtime_settings.py`, the Dockerfile, and CI.

---

## Findings

### CRITICAL — SSRF via redirect following (`api.py:52`)

```python
response = await client.get(url, follow_redirects=True)
```

`validate_url()` checks the host of the **initial** URL, but httpx silently follows 302 redirects to arbitrary destinations. An attacker hosts a page on an allowed domain that redirects to `http://169.254.169.254/latest/meta-data/` (cloud instance metadata) or any internal service. This completely bypasses the allowlist.

**Fix:** Set `follow_redirects=False`. If redirects are needed, implement a custom redirect handler that re-validates each hop's host against the allowlist.

---

### CRITICAL — Default-open allowlist (`api.py:44-46`, `runtime_settings.py:7`)

```python
allowed_hosts: list[str] = []
# ...
if allowed and host not in allowed:  # empty list is falsy — check is skipped
```

When `CACHER_ALLOWED_HOSTS` is unset (the default), **any URL is permitted**, enabling full SSRF to internal networks, cloud metadata, localhost services, etc.

**Fix:** Fail closed — either require the env var to be set (no default), or default to rejecting all hosts when the list is empty. Change the check to:
```python
if not allowed or host not in allowed:
    raise ValueError(...)
```

---

### HIGH — No private/internal IP blocking (`api.py:52`)

Even with a correctly configured allowlist, DNS rebinding can bypass host-string checks. An attacker registers `evil.allowed.com` resolving to `127.0.0.1`. The host string passes validation, but the request hits localhost.

**Fix:** After DNS resolution (or via httpx transport hooks), validate that the resolved IP is not in RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), or other non-routable ranges.

---

### HIGH — No response size limit (`api.py:53`)

```python
body=response.content,  # reads entire body into memory
```

An attacker can point the proxy at a URL serving gigabytes of data, exhausting server memory.

**Fix:** Use `httpx` streaming with a size cap, e.g. read in chunks up to a max (e.g., 10MB) and abort if exceeded.

---

### MEDIUM — No upstream timeout configured (`api.py:28`)

```python
async with httpx.AsyncClient() as client:  # default timeout = 5s, but not explicit
```

httpx defaults to 5s, but this should be explicit. More importantly, the global `lock` is held during the fetch (`api.py:80-82`), so a slow upstream blocks **all** cache-miss requests.

**Fix:** Set an explicit, short timeout: `httpx.AsyncClient(timeout=10.0)`. Consider per-URL locking instead of a global lock.

---

### MEDIUM — Unbounded cache / no eviction (`api.py:23`)

```python
cache: dict[str, CachedResponse] = {}  # grows forever
```

No TTL, no max-size, no LRU eviction. An attacker requesting many distinct URLs causes OOM. Error responses (500s, etc.) are also cached permanently.

**Fix:** Add TTL and max-entry-count eviction. Don't cache non-2xx responses, or give them a short negative-cache TTL.

---

### MEDIUM — Global lock serializes all misses (`api.py:24`, `api.py:79-82`)

A single `asyncio.Lock()` serializes all cache-miss fetches. One slow upstream request blocks every other user's cache miss, even for unrelated URLs.

**Fix:** Use per-URL locking (e.g., a dict of locks keyed by URL) to limit contention.

---

### MEDIUM — No rate limiting on `/refresh` (`api.py:86-91`)

`/refresh` always fetches upstream, ignoring the cache. An attacker can use this to amplify traffic to upstream targets or DoS the proxy itself.

**Fix:** Add rate limiting, at minimum on `/refresh`.

---

### LOW — FastAPI docs exposed by default

`/docs`, `/redoc`, and `/openapi.json` are served by default, revealing the full API schema.

**Fix:** Disable in production: `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)`.

---

### LOW — X-Cache header enables cache probing

The `X-Cache: hit/miss` header tells an attacker whether another user has previously requested a given URL.

**Fix:** Consider removing this header in production, or accept the risk if operational observability is more important.

---

### LOW — No port restriction in URL validation

An attacker can port-scan internal hosts: `http://internal:22/`, `http://internal:3306/`, etc. The allowlist checks the hostname but not the port.

**Fix:** Restrict to ports 80/443, or make allowed ports configurable.

---

## Recommended Fix Priority

| Priority | Issue | File | Effort |
|----------|-------|------|--------|
| P0 | Redirect-following bypasses allowlist | `api.py:52` | Small |
| P0 | Default-open allowlist | `runtime_settings.py:7`, `api.py:44-46` | Small |
| P1 | Private IP blocking | `api.py` (new validation) | Medium |
| P1 | Response size limit | `api.py:52-53` | Small |
| P2 | Explicit timeout | `api.py:28` | Trivial |
| P2 | Cache eviction / TTL | `api.py:23` | Medium |
| P2 | Per-URL locking | `api.py:24` | Medium |
| P2 | Rate limiting on /refresh | `api.py` | Medium |
| P3 | Disable docs in prod | `api.py:33` | Trivial |
| P3 | Port restriction | `api.py:validate_url` | Small |

## Verification

After fixes are applied:
- `uv run pytest -v` — existing tests pass
- New tests covering: redirect to private IP blocked, empty allowlist rejects requests, oversized response aborted, error responses not cached (or expire), port-restricted URLs rejected
- Manual: `curl "http://localhost:8000/get?url=http://169.254.169.254/latest/meta-data/"` returns 422/403
- Manual: set up a redirect chain from allowed host to internal IP, confirm it's blocked
