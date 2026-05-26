import pytest
from pydantic import ValidationError

import cacher.api as cacher_api
from cacher.api import validate_url
from cacher.runtime_settings import Settings


def test_valid_url(monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["example.com"])
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


def test_empty_allowed_hosts_rejects_all():
    """Settings must reject an empty allowlist at construction time."""
    with pytest.raises(ValidationError, match="non-empty list"):
        Settings(allowed_hosts=[])


def test_localhost_blocked_even_if_allowlisted(monkeypatch):
    """localhost is explicitly blocked regardless of the allowlist."""
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["localhost"])
    with pytest.raises(ValueError, match="Host not allowed"):
        validate_url("http://localhost/x")


def test_private_ipv4_blocked(monkeypatch):
    """Literal RFC 1918 addresses must be rejected."""
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["192.168.1.1"])
    with pytest.raises(ValueError, match="Host not allowed"):
        validate_url("http://192.168.1.1/x")


def test_loopback_ip_blocked(monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["127.0.0.1"])
    with pytest.raises(ValueError, match="Host not allowed"):
        validate_url("http://127.0.0.1/x")


def test_metadata_ip_blocked(monkeypatch):
    """Cloud instance metadata address must be rejected."""
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["169.254.169.254"])
    with pytest.raises(ValueError, match="Host not allowed"):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_nonstandard_port_blocked(monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["example.com"])
    with pytest.raises(ValueError, match="Port not allowed"):
        validate_url("http://example.com:8080/x")


def test_standard_ports_allowed(monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["example.com"])
    # Explicit port 80 and 443 are fine
    assert validate_url("http://example.com:80/x")
    assert validate_url("https://example.com:443/x")


async def test_get_invalid_url_422(client):
    r = await client.get("/get", params={"url": "not-a-url"})
    assert r.status_code == 422


async def test_get_disallowed_host_422(client, monkeypatch):
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", ["allowed.com"])
    r = await client.get("/get", params={"url": "http://blocked.com/x"})
    assert r.status_code == 422


async def test_get_empty_allowlist_422(client, monkeypatch):
    """Fail-closed: empty allowlist rejects all requests at the HTTP layer."""
    monkeypatch.setattr(cacher_api.settings, "allowed_hosts", [])
    r = await client.get("/get", params={"url": "http://testupstream/payload"})
    assert r.status_code == 422
