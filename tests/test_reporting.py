from decimal import Decimal
from types import SimpleNamespace

from src.activities.reporting.exporter import (
    export_bugcrowd,
    export_hackerone,
    export_markdown,
)
from src.db.models.finding import Severity


def _finding(**overrides):
    data = {
        "title": "IDOR exposes invoice",
        "severity": Severity.high,
        "vuln_type": "IDOR",
        "summary": "Users can access another invoice.",
        "vulnerability_details": "The invoice id is sequential.",
        "steps_to_reproduce": "Log in, change the id, reload.",
        "impact": "Unauthorized invoice disclosure.",
        "recommended_fix": "Authorize invoice access server-side.",
        "confidence_score": Decimal("0.90"),
        "payout_amount": Decimal("500.00"),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_markdown_export_contains_core_fields():
    report = export_markdown(
        _finding(),
        SimpleNamespace(name="Example Program"),
        SimpleNamespace(value="https://api.example.com"),
    )

    assert "# IDOR exposes invoice" in report
    assert "**Program:** Example Program" in report
    assert "**Severity:** HIGH" in report
    assert "**Confidence:** 90%" in report


def test_exporters_render_blank_missing_fields():
    finding = _finding(summary="", vulnerability_details=None)

    markdown = export_markdown(finding, None, None)
    hackerone = export_hackerone(finding, None, None)

    assert "_[not filled in]_" in markdown
    assert "_[not filled in]_" in hackerone


def test_bugcrowd_export_maps_severity_to_priority():
    report = export_bugcrowd(_finding(severity=Severity.critical), None, None)

    assert "P1 (critical)" in report
