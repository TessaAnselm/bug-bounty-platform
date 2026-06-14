"""#3 — Repeater success-path: a mocked successful send stores the exchange,
caps the response body, and shows redacted response headers."""
import asyncio
from uuid import uuid4

import src.api.routers.repeater as rp
from src.db.models import HuntSession, Program, ProgramStatus

_PROG = uuid4()
_ASSET = uuid4()
_added = []  # captures HttpExchange objects added across the (re-opened) sessions


class _Empty:
    def scalars(self):
        return self

    def all(self):
        return []


class _SuccessSession:
    """Fake DB session: serves a hunt + bugcrowd program (so no required header),
    returns empty result sets, and captures any added exchange."""
    def __init__(self, _engine):
        self.hunt = HuntSession(id=uuid4(), program_id=_PROG, asset_id=_ASSET)
        self.program = Program(
            id=_PROG, name="P", platform="bugcrowd",
            scope=["*.example.com"], out_of_scope=[],
            status=ProgramStatus.active, constraints={},
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, model, _id):
        if model is HuntSession:
            return self.hunt
        if model is Program:
            return self.program
        return None

    def execute(self, _stmt):
        return _Empty()

    def add(self, obj):
        _added.append(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()


class _FakeResp:
    def __init__(self):
        self.status_code = 200
        self.headers = {"Content-Type": "application/json", "Set-Cookie": "sid=secret"}
        self.text = "A" * (rp._MAX_BODY + 5000)  # bigger than the cap


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method, url, headers=None, content=None):
        return _FakeResp()


def test_send_success_stores_caps_and_redacts(monkeypatch):
    _added.clear()
    captured = {}

    monkeypatch.setattr(rp, "Session", _SuccessSession)
    monkeypatch.setattr(rp, "engine", object())
    monkeypatch.setattr(rp, "is_blocked_host", lambda h: False)   # skip DNS in tests
    monkeypatch.setattr(rp.httpx, "AsyncClient", _FakeClient)

    def fake_render(request, session_id, program_info, history, *, form,
                    response=None, error=None, findings=None, compliance=None, api_key=""):
        captured["response"] = response
        captured["error"] = error
        return {"ok": True}

    monkeypatch.setattr(rp, "_render", fake_render)

    asyncio.run(rp.send_request(
        request=None,
        hunt_session_id=str(uuid4()),
        method="get",
        url="https://api.example.com/v1/x",
        headers="X-Test: 1",
        body="",
        label="loop test",
        api_key="session",
    ))

    # success path
    assert captured["error"] is None
    resp = captured["response"]
    assert resp["status"] == 200
    assert len(resp["body"]) == rp._MAX_BODY                  # response body capped
    assert resp["headers"]["Set-Cookie"] == "<redacted>"     # displayed headers redacted

    # exchange persisted correctly
    assert len(_added) == 1
    ex = _added[0]
    assert ex.request_method == "GET"
    assert ex.request_url == "https://api.example.com/v1/x"
    assert ex.response_status == 200
    assert len(ex.response_body) == rp._MAX_BODY             # stored body also capped
    assert ex.label == "loop test"
