"""Tests for the Repeater compliance/safety guards and wiring."""
import asyncio
from uuid import uuid4

import src.lib.compliance as comp
import src.api.routers.repeater as repeater_router
from src.db.models import HuntSession, Program, ProgramStatus


def test_ssrf_guard_blocks_private_and_loopback():
    assert comp.is_blocked_host("127.0.0.1")
    assert comp.is_blocked_host("10.0.0.1")
    assert comp.is_blocked_host("192.168.1.1")
    assert comp.is_blocked_host("169.254.169.254")  # cloud metadata endpoint
    assert comp.is_blocked_host("")
    assert comp.is_blocked_host(None)


def test_ssrf_guard_allows_public_ip():
    # IP literal — no DNS needed, safe offline
    assert comp.is_blocked_host("8.8.8.8") is False


def test_ssrf_guard_blocks_hostname_that_resolves_private(monkeypatch):
    monkeypatch.setattr(
        comp.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("10.0.0.7", 0))],
    )

    assert comp.is_blocked_host("internal.example.com") is True


def test_ssrf_guard_allows_hostname_when_all_addresses_public(monkeypatch):
    monkeypatch.setattr(
        comp.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))],
    )

    assert comp.is_blocked_host("example.com") is False


def test_compliance_header_for_hackerone(monkeypatch):
    monkeypatch.setattr(comp, "HACKERONE_RESEARCH_USERNAME", "tester")
    assert comp.compliance_headers("hackerone") == {"X-HackerOne-Research": "tester"}
    assert comp.compliance_headers("bugcrowd") == {}
    monkeypatch.setattr(comp, "HACKERONE_RESEARCH_USERNAME", "")
    assert comp.compliance_headers("hackerone") == {}


def test_min_send_interval_is_exact():
    assert comp.min_send_interval({"rate_limit_rpm": 180}) == 60.0 / 180  # 3 rps
    assert comp.min_send_interval({"rate_limit_rpm": 30}) == 2.0          # slow cap honored
    assert comp.min_send_interval({}, default_rps=3) == 1.0 / 3
    assert comp.min_send_interval(None, default_rps=3) == 1.0 / 3


def test_program_rate_rps_floors_to_at_least_one():
    assert comp.program_rate_rps({"rate_limit_rpm": 180}) == 3
    assert comp.program_rate_rps({"rate_limit_rpm": 30}) == 1
    assert comp.program_rate_rps({}) is None
    assert comp.program_rate_rps(None) is None


def test_redact_headers_masks_secrets():
    r = comp.redact_headers({
        "Cookie": "s",
        "Authorization": "Bearer x",
        "X-API-Key": "secret",
        "Proxy-Authorization": "proxy-secret",
        "Set-Cookie": "session=secret",
        "User-Agent": "ua",
    })
    assert r["Cookie"] == "<redacted>"
    assert r["Authorization"] == "<redacted>"
    assert r["X-API-Key"] == "<redacted>"
    assert r["Proxy-Authorization"] == "<redacted>"
    assert r["Set-Cookie"] == "<redacted>"
    assert r["User-Agent"] == "ua"


def test_redact_text_masks_common_secret_shapes():
    redacted = comp.redact_text(
        '{"access_token":"abc123","password":"hunter2"}&csrf_token=tok Bearer abc.def'
    )

    assert "abc123" not in redacted
    assert "hunter2" not in redacted
    assert "csrf_token=tok" not in redacted
    assert "abc.def" not in redacted
    assert "<redacted>" in redacted


def test_host_from_url():
    assert comp.host_from_url("https://api.example.com/v1/x?y=1") == "api.example.com"


def test_parse_headers_ignores_malformed_lines_and_preserves_colons():
    headers = repeater_router._parse_headers(
        "Authorization: Bearer abc.def\n"
        "broken line\n"
        "X-Test: value:with:colons\n"
        ": missing-name\n"
    )

    assert headers == {
        "Authorization": "Bearer abc.def",
        "X-Test": "value:with:colons",
    }


def test_blocked_header_names_identifies_unsafe_request_headers():
    blocked = repeater_router._blocked_header_names({
        "Host": "evil.example.com",
        "Content-Length": "999",
        "User-Agent": "ua",
    })

    assert blocked == ["Content-Length", "Host"]


def test_repeater_wiring_importable():
    from src.api.routers import repeater
    from src.db.models import HttpExchange
    from src.mcp.resources.exchanges import list_exchanges_for_session
    assert repeater.router and HttpExchange and list_exchanges_for_session


def test_app_registers_repeater_routes():
    from src.api.main import app
    paths = {r.path for r in app.routes}
    assert "/repeater" in paths and "/repeater/send" in paths


class _ScalarRows:
    def scalars(self):
        return self

    def all(self):
        return []


class _FakeSession:
    def __init__(self, _engine):
        self.program_id = uuid4()
        self.hunt = HuntSession(
            id=uuid4(),
            program_id=self.program_id,
            asset_id=uuid4(),
        )
        self.program = Program(
            id=self.program_id,
            name="Example Program",
            platform="hackerone",
            scope=["*.example.com"],
            out_of_scope=["admin.example.com"],
            status=ProgramStatus.active,
            constraints={},
        )

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def get(self, model, _id):
        if model is HuntSession:
            return self.hunt
        if model is Program:
            return self.program
        return None

    def execute(self, _stmt):
        return _ScalarRows()


def _install_route_fakes(monkeypatch):
    monkeypatch.setattr(repeater_router, "Session", _FakeSession)
    monkeypatch.setattr(repeater_router, "engine", object())
    monkeypatch.setattr(
        repeater_router,
        "_render",
        lambda _request, session_id, program_info, history, **kwargs: {
            "session_id": session_id,
            "program": program_info,
            "history": history,
            **kwargs,
        },
    )


def test_send_request_blocks_private_host_before_network(monkeypatch):
    _install_route_fakes(monkeypatch)
    attempted = {"value": False}

    class FailIfUsed:
        def __init__(self, *_args, **_kwargs):
            attempted["value"] = True
            raise AssertionError("network client should not be created")

    monkeypatch.setattr(repeater_router.httpx, "AsyncClient", FailIfUsed)
    monkeypatch.setattr(repeater_router, "is_blocked_host", lambda host: True)

    result = asyncio.run(
        repeater_router.send_request(
            None,
            hunt_session_id=str(uuid4()),
            method="GET",
            url="http://127.0.0.1/",
            headers="",
            body="",
            label="",
            api_key="session",
        )
    )

    assert attempted["value"] is False
    assert "SSRF guard" in result["error"]


def test_send_request_blocks_out_of_scope_before_network(monkeypatch):
    _install_route_fakes(monkeypatch)
    attempted = {"value": False}

    class FailIfUsed:
        def __init__(self, *_args, **_kwargs):
            attempted["value"] = True
            raise AssertionError("network client should not be created")

    monkeypatch.setattr(repeater_router.httpx, "AsyncClient", FailIfUsed)
    monkeypatch.setattr(repeater_router, "is_blocked_host", lambda host: False)

    result = asyncio.run(
        repeater_router.send_request(
            None,
            hunt_session_id=str(uuid4()),
            method="GET",
            url="https://outside.example.net/path",
            headers="",
            body="",
            label="",
            api_key="session",
        )
    )

    assert attempted["value"] is False
    assert "out of scope" in result["error"]


def test_send_request_blocks_host_header_before_network(monkeypatch):
    _install_route_fakes(monkeypatch)
    attempted = {"value": False}

    class FailIfUsed:
        def __init__(self, *_args, **_kwargs):
            attempted["value"] = True
            raise AssertionError("network client should not be created")

    monkeypatch.setattr(repeater_router.httpx, "AsyncClient", FailIfUsed)
    monkeypatch.setattr(repeater_router, "is_blocked_host", lambda host: False)

    result = asyncio.run(
        repeater_router.send_request(
            None,
            hunt_session_id=str(uuid4()),
            method="GET",
            url="https://api.example.com/path",
            headers="Host: outside.example.net",
            body="",
            label="",
            api_key="session",
        )
    )

    assert attempted["value"] is False
    assert "Blocked request header" in result["error"]


def test_send_request_enforces_request_body_size_before_network(monkeypatch):
    _install_route_fakes(monkeypatch)
    attempted = {"value": False}

    class FailIfUsed:
        def __init__(self, *_args, **_kwargs):
            attempted["value"] = True
            raise AssertionError("network client should not be created")

    monkeypatch.setattr(repeater_router.httpx, "AsyncClient", FailIfUsed)
    monkeypatch.setattr(repeater_router, "is_blocked_host", lambda host: False)

    result = asyncio.run(
        repeater_router.send_request(
            None,
            hunt_session_id=str(uuid4()),
            method="POST",
            url="https://api.example.com/path",
            headers="",
            body="x" * (repeater_router._MAX_REQUEST_BODY + 1),
            label="",
            api_key="session",
        )
    )

    assert attempted["value"] is False
    assert "Request body is too large" in result["error"]
