import time


import cacher.api as cacher_api


async def test_cache_miss(client):
    r = await client.get("/get", params={"url": "http://testupstream/payload"})
    assert r.status_code == 200
    assert r.headers["x-cache"] == "miss"
    assert r.json() == {"msg": "hello"}


async def test_cache_hit(client):
    r1 = await client.get("/get", params={"url": "http://testupstream/payload"})
    r2 = await client.get("/get", params={"url": "http://testupstream/payload"})
    assert r1.headers["x-cache"] == "miss"
    assert r2.headers["x-cache"] == "hit"
    assert r1.content == r2.content


async def test_different_urls_independent(client):
    r1 = await client.get("/get", params={"url": "http://testupstream/payload"})
    r2 = await client.get("/get", params={"url": "http://testupstream/text"})
    assert r1.headers["x-cache"] == "miss"
    assert r2.headers["x-cache"] == "miss"


async def test_upstream_error_proxied(client):
    r = await client.get("/get", params={"url": "http://testupstream/error"})
    assert r.status_code == 500


async def test_upstream_error_not_cached(client):
    """5xx responses must not be cached — transient failures should not poison
    the cache permanently."""
    url = "http://testupstream/error"
    r1 = await client.get("/get", params={"url": url})
    assert r1.status_code == 500
    assert url not in cacher_api.cache


async def test_content_type_preserved(client):
    r = await client.get("/get", params={"url": "http://testupstream/text"})
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]


async def test_slow_endpoint_cached(client):
    t0 = time.monotonic()
    r1 = await client.get("/get", params={"url": "http://testupstream/slow"})
    elapsed_miss = time.monotonic() - t0
    assert r1.headers["x-cache"] == "miss"
    assert elapsed_miss >= 0.2, f"Expected upstream delay >= 0.2s, got {elapsed_miss:.3f}s"

    t1 = time.monotonic()
    r2 = await client.get("/get", params={"url": "http://testupstream/slow"})
    elapsed_hit = time.monotonic() - t1
    assert r2.headers["x-cache"] == "hit"
    assert r2.content == r1.content
    assert elapsed_hit < 0.1, f"Expected cache hit to be near-instant, got {elapsed_hit:.3f}s"


async def test_redirect_not_followed(client):
    """Redirects must not be followed — doing so would bypass host validation."""
    r = await client.get("/get", params={"url": "http://testupstream/redirect"})
    # The redirect response itself is returned, not the redirect target
    assert r.status_code == 302


async def test_response_too_large_raises(client, monkeypatch):
    """Responses exceeding MAX_RESPONSE_BODY_BYTES must be rejected."""
    monkeypatch.setattr(cacher_api.settings, "max_response_body_bytes", 100)
    # /large returns 200 bytes, which exceeds the patched 100-byte limit
    r = await client.get("/get", params={"url": "http://testupstream/large"})
    assert r.status_code == 502


async def test_upstream_query_params_forwarded(client):
    """Query parameters in the upstream URL must be forwarded verbatim."""
    url = "http://testupstream/echo-params?foo=bar&baz=qux"
    r = await client.get("/get", params={"url": url})
    assert r.status_code == 200
    assert r.json() == {"foo": "bar", "baz": "qux"}


async def test_urls_differing_only_in_query_params_cached_independently(client):
    """Two URLs that share a path but differ in query params are separate cache entries."""
    url_a = "http://testupstream/echo-params?key=alpha"
    url_b = "http://testupstream/echo-params?key=beta"

    r_a1 = await client.get("/get", params={"url": url_a})
    r_b = await client.get("/get", params={"url": url_b})
    r_a2 = await client.get("/get", params={"url": url_a})

    assert r_a1.json() == {"key": "alpha"}
    assert r_b.json() == {"key": "beta"}
    assert r_a1.headers["x-cache"] == "miss"
    assert r_b.headers["x-cache"] == "miss"
    assert r_a2.headers["x-cache"] == "hit"
