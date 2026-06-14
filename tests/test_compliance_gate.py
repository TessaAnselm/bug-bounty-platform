"""#5 — per-program compliance checklist + activation gate."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import src.api.routers.programs as pr
from src.db.models.program import ProgramStatus

_ALL_ATTESTATIONS = {
    "terms_accepted": True,
    "out_of_scope_reviewed": True,
    "rate_limit_confirmed": True,
    "active_scanning_confirmed": True,
    "prohibited_tools": "no scanners; no DoS",
}


def _prog(**kw):
    base = dict(id=uuid4(), status=ProgramStatus.draft, scope=["a.example.com"],
                platform="bugcrowd", compliance={})
    base.update(kw)
    return SimpleNamespace(**base)


# ── checklist logic ──────────────────────────────────────────────────────────
def test_incomplete_by_default():
    p = _prog()
    status = pr.compliance_status(p)
    assert status["in_scope_loaded"] is True
    assert status["required_headers_configured"] is True   # bugcrowd → no header needed
    assert status["terms_accepted"] is False
    assert pr.compliance_complete(p) is False


def test_complete_when_all_attested():
    p = _prog(compliance=dict(_ALL_ATTESTATIONS))
    assert pr.compliance_complete(p) is True


def test_no_scope_blocks_completion():
    p = _prog(scope=[], compliance=dict(_ALL_ATTESTATIONS))
    assert pr.compliance_status(p)["in_scope_loaded"] is False
    assert pr.compliance_complete(p) is False


def test_hackerone_requires_configured_header(monkeypatch):
    p = _prog(platform="hackerone", compliance=dict(_ALL_ATTESTATIONS))
    monkeypatch.setattr(pr, "HACKERONE_RESEARCH_USERNAME", "")
    assert pr.compliance_status(p)["required_headers_configured"] is False
    assert pr.compliance_complete(p) is False
    monkeypatch.setattr(pr, "HACKERONE_RESEARCH_USERNAME", "tester")
    assert pr.compliance_complete(p) is True


# ── activation gate ──────────────────────────────────────────────────────────
class _S:
    def __init__(self, program):
        self.program = program

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, _model, _id):
        return self.program

    def commit(self):
        pass


def _patch(monkeypatch, program):
    monkeypatch.setattr(pr, "Session", lambda _engine: _S(program))
    monkeypatch.setattr(pr, "engine", object())


def test_activation_blocked_when_incomplete(monkeypatch):
    p = _prog(compliance={})  # nothing attested
    _patch(monkeypatch, p)
    resp = asyncio.run(pr.update_status(program_id=str(p.id), request=None, status="active", api_key="x"))
    assert resp.status_code == 400
    assert p.status == ProgramStatus.draft  # not activated


def test_activation_allowed_when_complete(monkeypatch):
    p = _prog(compliance=dict(_ALL_ATTESTATIONS))
    _patch(monkeypatch, p)
    resp = asyncio.run(pr.update_status(program_id=str(p.id), request=None, status="active", api_key="x"))
    assert resp.status_code == 303  # redirect = success
    assert p.status == ProgramStatus.active
