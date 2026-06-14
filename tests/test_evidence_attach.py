"""#4 — Evidence attach/detach rules. Most importantly: an exchange from a
different asset cannot be attached to a finding."""
import asyncio
from uuid import uuid4

import src.api.routers.findings as fr
from src.db.models import Finding, HttpExchange, Severity, FindingStatus


def _finding(program_id, asset_id):
    return Finding(
        id=uuid4(), program_id=program_id, asset_id=asset_id,
        title="t", vuln_type="x", severity=Severity.medium, status=FindingStatus.draft,
    )


def _exchange(program_id, asset_id, finding_id=None, is_evidence=False):
    return HttpExchange(
        id=uuid4(), program_id=program_id, asset_id=asset_id,
        request_method="GET", request_url="https://x.example.com",
        finding_id=finding_id, is_evidence=is_evidence,
    )


class _FakeSession:
    """Serves one finding + one exchange; commit() is a no-op (mutations happen
    on the live objects we then assert against)."""
    def __init__(self, finding=None, ex=None):
        self._finding = finding
        self._ex = ex

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, model, _id):
        if model is Finding:
            return self._finding
        if model is HttpExchange:
            return self._ex
        return None

    def commit(self):
        pass


def _patch(monkeypatch, finding, ex):
    monkeypatch.setattr(fr, "Session", lambda _engine: _FakeSession(finding, ex))
    monkeypatch.setattr(fr, "engine", object())


def test_attach_same_asset_attaches(monkeypatch):
    prog, asset = uuid4(), uuid4()
    f, ex = _finding(prog, asset), _exchange(prog, asset)
    _patch(monkeypatch, f, ex)
    asyncio.run(fr.attach_evidence(finding_id=f.id, request=None, exchange_id=ex.id, api_key="x"))
    assert ex.finding_id == f.id and ex.is_evidence is True


def test_attach_wrong_asset_rejected(monkeypatch):
    prog = uuid4()
    f, ex = _finding(prog, uuid4()), _exchange(prog, uuid4())  # same program, different asset
    _patch(monkeypatch, f, ex)
    asyncio.run(fr.attach_evidence(finding_id=f.id, request=None, exchange_id=ex.id, api_key="x"))
    assert ex.finding_id is None and ex.is_evidence is False


def test_attach_wrong_program_rejected(monkeypatch):
    f, ex = _finding(uuid4(), uuid4()), _exchange(uuid4(), uuid4())  # different program
    _patch(monkeypatch, f, ex)
    asyncio.run(fr.attach_evidence(finding_id=f.id, request=None, exchange_id=ex.id, api_key="x"))
    assert ex.finding_id is None and ex.is_evidence is False


def test_attach_assetless_finding_allows_any_asset(monkeypatch):
    prog = uuid4()
    f, ex = _finding(prog, None), _exchange(prog, uuid4())  # finding not tied to an asset
    _patch(monkeypatch, f, ex)
    asyncio.run(fr.attach_evidence(finding_id=f.id, request=None, exchange_id=ex.id, api_key="x"))
    assert ex.finding_id == f.id and ex.is_evidence is True


def test_detach_clears_evidence(monkeypatch):
    fid = uuid4()
    ex = _exchange(uuid4(), uuid4(), finding_id=fid, is_evidence=True)
    monkeypatch.setattr(fr, "Session", lambda _engine: _FakeSession(None, ex))
    monkeypatch.setattr(fr, "engine", object())
    asyncio.run(fr.detach_evidence(finding_id=fid, exchange_id=ex.id, request=None, api_key="x"))
    assert ex.finding_id is None and ex.is_evidence is False
