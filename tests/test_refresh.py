import cacher.api as cacher_api


async def test_refresh_returns_refresh_header(client):
    r = await client.post("/refresh", params={"url": "http://testupstream/payload"})
    assert r.status_code == 200
    assert r.headers["x-cache"] == "refresh"


async def test_refresh_updates_cache(client):
    url = "http://testupstream/counter"

    # First GET: cache miss, upstream fetch → counter=1
    r = await client.get("/get", params={"url": url})
    assert r.headers["x-cache"] == "miss"
    assert r.json() == {"count": 1}

    # Multiple subsequent GETs: all cache hits, counter stays at 1
    for _ in range(3):
        r = await client.get("/get", params={"url": url})
        assert r.headers["x-cache"] == "hit"
        assert r.json() == {"count": 1}

    # Refresh: fetches again → counter=2
    r = await client.post("/refresh", params={"url": url})
    assert r.headers["x-cache"] == "refresh"
    assert r.json() == {"count": 2}

    # Multiple subsequent GETs: all cache hits, counter stays at 2
    for _ in range(3):
        r = await client.get("/get", params={"url": url})
        assert r.headers["x-cache"] == "hit"
        assert r.json() == {"count": 2}


async def test_refresh_populates_empty_cache(client):
    url = "http://testupstream/payload"

    r = await client.post("/refresh", params={"url": url})
    assert r.headers["x-cache"] == "refresh"
    assert r.json() == {"msg": "hello"}

    r2 = await client.get("/get", params={"url": url})
    assert r2.headers["x-cache"] == "hit"
    assert r2.json() == {"msg": "hello"}


async def test_refresh_error_not_cached(client):
    """5xx refresh responses must not be stored — a subsequent GET should re-fetch."""
    url = "http://testupstream/error"

    r = await client.post("/refresh", params={"url": url})
    assert r.status_code == 500
    assert url not in cacher_api.cache
