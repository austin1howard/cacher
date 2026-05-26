import time


async def test_cache_miss(client):
    r = await client.get("/get", params={"url": "http://localhost/payload"})
    assert r.status_code == 200
    assert r.headers["x-cache"] == "miss"
    assert r.json() == {"msg": "hello"}


async def test_cache_hit(client):
    r1 = await client.get("/get", params={"url": "http://localhost/payload"})
    r2 = await client.get("/get", params={"url": "http://localhost/payload"})
    assert r1.headers["x-cache"] == "miss"
    assert r2.headers["x-cache"] == "hit"
    assert r1.content == r2.content


async def test_different_urls_independent(client):
    r1 = await client.get("/get", params={"url": "http://localhost/payload"})
    r2 = await client.get("/get", params={"url": "http://localhost/text"})
    assert r1.headers["x-cache"] == "miss"
    assert r2.headers["x-cache"] == "miss"


async def test_upstream_error_proxied(client):
    r = await client.get("/get", params={"url": "http://localhost/error"})
    assert r.status_code == 500


async def test_content_type_preserved(client):
    r = await client.get("/get", params={"url": "http://localhost/text"})
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]


async def test_slow_endpoint_cached(client):
    t0 = time.monotonic()
    r1 = await client.get("/get", params={"url": "http://localhost/slow"})
    elapsed_miss = time.monotonic() - t0
    assert r1.headers["x-cache"] == "miss"
    assert elapsed_miss >= 0.2, f"Expected upstream delay >= 0.2s, got {elapsed_miss:.3f}s"

    t1 = time.monotonic()
    r2 = await client.get("/get", params={"url": "http://localhost/slow"})
    elapsed_hit = time.monotonic() - t1
    assert r2.headers["x-cache"] == "hit"
    assert r2.content == r1.content
    assert elapsed_hit < 0.1, f"Expected cache hit to be near-instant, got {elapsed_hit:.3f}s"
