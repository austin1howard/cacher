"""
Test infrastructure for cacher.

Architecture overview
---------------------
The cacher app fetches upstream URLs using an httpx.AsyncClient stored on
app.state.client (set by the lifespan in api.py). In tests we skip the real
lifespan and inject a fake upstream client instead, so nothing ever touches
the network.

That fake client is backed by httpx.ASGITransport — an httpx transport that
routes requests directly into a local ASGI app (dummy_app below) as in-process
coroutine calls. From the cacher's perspective it looks exactly like a normal
httpx client making real HTTP requests; the only difference is that the
"network" is just a function call into dummy_app.

Why ASGITransport instead of mocking httpx?
  Mocking httpx.AsyncClient.get() would test that we call the mock correctly,
  not that cacher integrates correctly with its own HTTP client. Using a real
  (if in-process) ASGI app exercises the full request/response path through
  httpx, including header handling, status codes, and content-type forwarding.

Why AsyncClient + ASGITransport for the test client (not Starlette's TestClient)?
  TestClient is synchronous and runs the ASGI app in a background thread. That
  means every "concurrent" request in a test is actually serialised across a
  thread boundary, and asyncio.Lock behaves differently (or incorrectly) because
  coroutines are not all on the same event loop. Using an async test client with
  ASGITransport keeps everything on one event loop, so asyncio.gather produces
  genuine coroutine interleaving and the lock contention tests reflect real
  runtime behaviour.

Request flow in tests
---------------------
  test code
    └─ async httpx.AsyncClient (transport=ASGITransport(app=cacher_app))
         └─ cacher route handler
              └─ app.state.client.get(url)          ← injected by client fixture
                   └─ async httpx.AsyncClient (transport=ASGITransport(app=dummy_app))
                        └─ dummy route handler (no network, in-process)

Upstream hostname in tests
--------------------------
Tests use "http://testupstream/..." as the upstream base URL.  The host
"testupstream" is added to the allowed_hosts allowlist by the autouse
_set_allowed_hosts fixture so that validate_url() accepts it.  Using a
non-sensitive hostname (not "localhost") also exercises the security check
that blocks well-known loopback names.
"""

import os

# Must be set before cacher modules are imported so that Settings() sees it and
# passes the must_not_be_empty validator at construction time.
os.environ.setdefault("CACHER_ALLOWED_HOSTS", '["testupstream"]')

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from httpx import ASGITransport

import cacher.api as cacher_api
from cacher.api import app

# ---------------------------------------------------------------------------
# Dummy upstream app
#
# Each route models a specific behaviour we need to exercise in tests.
# The app is module-level so it's created once and shared; state that must
# reset between tests (like the counter) is kept in a plain dict and cleared
# by an autouse fixture below.
# ---------------------------------------------------------------------------

dummy_app = FastAPI()
_counter: dict[str, int] = {"value": 0}


@dummy_app.get("/payload")
async def dummy_payload() -> dict:
    """Standard successful response — used for basic hit/miss/refresh tests."""
    return {"msg": "hello"}


@dummy_app.get("/slow")
async def dummy_slow() -> dict:
    """Sleeps before responding, giving other coroutines time to run.

    Used in concurrency tests to guarantee that the coroutine holding the
    asyncio.Lock actually yields during the upstream fetch, so other coroutines
    can stack up on the lock and exercise the double-checked locking pattern.
    """
    await asyncio.sleep(0.2)
    return {"msg": "slow"}


@dummy_app.get("/counter")
async def dummy_counter() -> dict:
    """Increments a counter on every call and returns the new value.

    Because the counter only goes up when cacher actually fetches from upstream,
    its value tells us exactly how many real fetches occurred — useful for
    asserting that the cache prevented redundant upstream calls.
    """
    _counter["value"] += 1
    return {"count": _counter["value"]}


@dummy_app.get("/error")
async def dummy_error() -> Response:
    """Returns a 500 so we can verify cacher proxies error status codes through."""
    return Response(status_code=500, content=b"internal error")


@dummy_app.get("/text")
async def dummy_text() -> PlainTextResponse:
    """Returns text/plain so we can verify content-type is preserved end-to-end."""
    return PlainTextResponse("hello text")


@dummy_app.get("/redirect")
async def dummy_redirect() -> RedirectResponse:
    """Returns a 302 to another path — used to verify redirects are not followed."""
    return RedirectResponse(url="http://testupstream/payload", status_code=302)


@dummy_app.get("/large")
async def dummy_large() -> Response:
    """Returns a body larger than MAX_RESPONSE_BODY_BYTES when that constant is
    monkeypatched to a small value in size-limit tests."""
    return Response(content=b"x" * 200, media_type="application/octet-stream")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset cacher's module-level cache dict and per-URL lock dict before and
    after every test.

    Both are intentionally global state in api.py (they live for the process
    lifetime in production). Without this fixture every test would inherit
    whatever a prior test cached, making tests order-dependent.
    """
    cacher_api.cache.clear()
    cacher_api._url_locks.clear()
    yield
    cacher_api.cache.clear()
    cacher_api._url_locks.clear()


@pytest.fixture(autouse=True)
def _reset_counter():
    """Reset the dummy upstream's fetch counter before every test."""
    _counter["value"] = 0


@pytest.fixture(autouse=True)
def _set_allowed_hosts(monkeypatch):
    """Allow 'testupstream' in every test.

    The allowlist now fails closed (empty list = reject all), so tests must
    explicitly permit the fake upstream hostname used in all test URLs.
    """
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["testupstream"])


@pytest.fixture
async def client():
    """Yield an async httpx client wired to cacher, with a fake upstream injected.

    Setup:
      1. Create an httpx.AsyncClient whose transport routes into dummy_app.
         This becomes app.state.client — the client cacher uses for upstream fetches.
      2. Create a second httpx.AsyncClient whose transport routes into the cacher app.
         This is what tests use to make requests.

    Both clients use ASGITransport so the entire request path stays in-process
    on a single event loop. No sockets, no threads, no network.
    """
    upstream = httpx.AsyncClient(transport=ASGITransport(app=dummy_app), base_url="http://testupstream")
    app.state.client = upstream  # inject — cacher's fetch_url will use this
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
    await upstream.aclose()
