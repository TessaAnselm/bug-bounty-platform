"""Tests for evidence -> report rendering (redaction + scaffolding + wiring)."""
from types import SimpleNamespace

from src.activities.reporting import exporter


def _ex(**kw):
    base = dict(
        request_method="GET",
        request_url="https://api.example.com/u/1",
        request_headers={"Cookie": "sess=secret", "User-Agent": "ua"},
        request_body=None,
        response_status=200,
        response_time_ms=42,
        response_body='{"access_token":"abc123","email":"a@b.com"}',
        label="acct A",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _finding(**kw):
    base = dict(
        title="IDOR in profile",
        vuln_type="IDOR",
        severity=SimpleNamespace(value="high"),
        confidence_score=None,
        payout_amount=None,
        summary="s",
        vulnerability_details="d",
        steps_to_reproduce=None,
        impact="i",
        recommended_fix="f",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_render_evidence_redacts_header_and_body_secrets():
    out = exporter.render_evidence([_ex()])
    assert "GET https://api.example.com/u/1" in out
    assert "<redacted>" in out          # Cookie header masked
    assert "sess=secret" not in out
    assert "access_token" in out        # key name preserved for context
    assert "abc123" not in out          # token value scrubbed


def test_render_evidence_empty_placeholder():
    assert "No request/response evidence" in exporter.render_evidence([])
    assert "No request/response evidence" in exporter.render_evidence(None)


def test_scaffold_steps_are_numbered_from_evidence():
    s = exporter.scaffold_steps([
        _ex(),
        _ex(request_url="https://api.example.com/u/2", label="acct B"),
    ])
    assert s.startswith("1. Send `GET https://api.example.com/u/1` (acct A) → observed `200`.")
    assert "2. Send `GET https://api.example.com/u/2` (acct B)" in s


def test_export_markdown_includes_evidence_and_scaffolds_steps():
    md = exporter.export_markdown(
        _finding(), SimpleNamespace(name="P"), SimpleNamespace(value="api.example.com"), [_ex()]
    )
    assert "## Evidence" in md
    assert "1. Send `GET" in md     # steps scaffolded (finding had none)
    assert "abc123" not in md       # redaction holds through the full report


def test_export_prefers_written_steps_over_scaffold():
    md = exporter.export_markdown(
        _finding(steps_to_reproduce="my exact steps"),
        SimpleNamespace(name="P"), SimpleNamespace(value="a"), [_ex()],
    )
    assert "my exact steps" in md


def test_findings_router_registers_evidence_routes():
    from src.api.main import app
    paths = {r.path for r in app.routes}
    assert "/findings/{finding_id}/evidence/attach" in paths
    assert "/findings/{finding_id}/evidence/{exchange_id}/detach" in paths
