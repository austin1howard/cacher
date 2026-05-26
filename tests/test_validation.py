import pytest

import cacher.api as cacher_api
from cacher.api import validate_url


def test_valid_url():
    result = validate_url("http://example.com/foo")
    assert "example.com" in result


def test_invalid_url_raises():
    with pytest.raises(ValueError, match="Invalid URL"):
        validate_url("not-a-url")


def test_disallowed_host_raises(monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["allowed.com"])
    with pytest.raises(ValueError, match="Host not allowed"):
        validate_url("http://blocked.com/x")


def test_allowed_host_passes(monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["example.com"])
    result = validate_url("http://example.com/x")
    assert "example.com" in result


def test_empty_allowed_hosts_permits_all(monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", [])
    result = validate_url("http://anything.io/x")
    assert result


async def test_get_invalid_url_422(client):
    r = await client.get("/get", params={"url": "not-a-url"})
    assert r.status_code == 422


async def test_get_disallowed_host_422(client, monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["allowed.com"])
    r = await client.get("/get", params={"url": "http://blocked.com/x"})
    assert r.status_code == 422
