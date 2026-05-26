import asyncio


async def test_concurrent_gets_single_fetch(client):
    """10 concurrent GETs for the same slow URL — only 1 upstream fetch should occur.

    The /slow endpoint sleeps 0.2s, guaranteeing the first coroutine yields while
    holding the lock, allowing the others to stack up and observe the double-checked
    locking: they block on the lock, then find the cache populated on the inner check.
    """
    url = "http://testupstream/slow"
    responses = await asyncio.gather(*[client.get("/get", params={"url": url}) for _ in range(10)])

    x_caches = [r.headers["x-cache"] for r in responses]
    assert x_caches.count("miss") == 1
    assert x_caches.count("hit") == 9


async def test_concurrent_gets_different_urls(client):
    """Concurrent GETs to distinct URLs all result in cache misses."""
    urls = [
        "http://testupstream/payload",
        "http://testupstream/text",
        "http://testupstream/counter",
    ]
    responses = await asyncio.gather(*[client.get("/get", params={"url": u}) for u in urls])
    for r in responses:
        assert r.headers["x-cache"] == "miss"


async def test_get_and_refresh_interleaved(client):
    """GET (instant cache hit) and refresh run concurrently; final state reflects the refresh."""
    url = "http://testupstream/counter"

    # Seed the cache: counter=1
    seed = await client.get("/get", params={"url": url})
    assert seed.json() == {"count": 1}

    # Fire GET + refresh concurrently.
    # GET sees the cache immediately (no lock needed) → hit with old value.
    # Refresh acquires lock, fetches counter=2, updates cache.
    get_r, refresh_r = await asyncio.gather(
        client.get("/get", params={"url": url}),
        client.post("/refresh", params={"url": url}),
    )
    assert get_r.headers["x-cache"] == "hit"
    assert refresh_r.headers["x-cache"] == "refresh"
    assert refresh_r.json() == {"count": 2}

    # After both settle, GET should return the refreshed value.
    final = await client.get("/get", params={"url": url})
    assert final.headers["x-cache"] == "hit"
    assert final.json() == {"count": 2}


async def test_multiple_concurrent_refreshes(client):
    """5 concurrent refreshes serialize through the lock, each doing one upstream fetch."""
    url = "http://testupstream/counter"
    responses = await asyncio.gather(*[client.post("/refresh", params={"url": url}) for _ in range(5)])

    for r in responses:
        assert r.headers["x-cache"] == "refresh"

    counts = sorted(r.json()["count"] for r in responses)
    assert counts == [1, 2, 3, 4, 5]
