"""#2 — DNS rebinding hardening: resolve+validate to a pinned public IP, then
connect to that exact IP while verifying TLS against the original hostname."""
import asyncio

import pytest

import src.api.routers.repeater as rp
import src.lib.compliance as comp


# ── resolve_public_ip ────────────────────────────────────────────────────────
def test_resolve_blocks_nonpublic_literals():
    assert comp.resolve_public_ip("127.0.0.1") is None
    assert comp.resolve_public_ip("10.0.0.1") is None
    assert comp.resolve_public_ip("169.254.169.254") is None   # cloud metadata
    assert comp.resolve_public_ip("") is None


def test_resolve_returns_public_literal():
    assert comp.resolve_public_ip("8.8.8.8") == "8.8.8.8"


def test_resolve_prefers_ipv4(monkeypatch):
    monkeypatch.setattr(comp.socket, "getaddrinfo", lambda *a, **k: [
        (None, None, None, None, ("2606:4700:4700::1111", 0)),
        (None, None, None, None, ("1.1.1.1", 0)),
    ])
    assert comp.resolve_public_ip("dns.example") == "1.1.1.1"


def test_resolve_blocks_if_any_address_private(monkeypatch):
    # A host with both a public and a private record is rejected entirely —
    # this is the rebinding defense.
    monkeypatch.setattr(comp.socket, "getaddrinfo", lambda *a, **k: [
        (None, None, None, None, ("93.184.216.34", 0)),
        (None, None, None, None, ("10.0.0.5", 0)),
    ])
    assert comp.resolve_public_ip("mixed.example") is None


# ── _PinnedTransport ─────────────────────────────────────────────────────────
def test_transport_pins_ip_and_sets_sni(monkeypatch):
    captured = {}

    async def fake_super(self, request):
        captured["host"] = request.url.host
        captured["sni"] = request.extensions.get("sni_hostname")
        return "OK"

    monkeypatch.setattr(rp.httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
    monkeypatch.setattr(rp, "resolve_public_ip", lambda h: "93.184.216.34")

    t = rp._PinnedTransport()
    req = rp.httpx.Request("GET", "https://api.example.com/v1/x")
    result = asyncio.run(t.handle_async_request(req))

    assert result == "OK"
    assert captured["host"] == "93.184.216.34"      # TCP target is the pinned IP
    assert captured["sni"] == "api.example.com"     # but TLS verifies the hostname


def test_transport_blocks_nonpublic(monkeypatch):
    monkeypatch.setattr(rp, "resolve_public_ip", lambda h: None)
    t = rp._PinnedTransport()
    req = rp.httpx.Request("GET", "https://internal.example.com/")
    with pytest.raises(rp.httpx.ConnectError):
        asyncio.run(t.handle_async_request(req))
