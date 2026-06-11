import uuid
from pathlib import Path
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Finding, Program, Asset, FindingStatus, Outcome, HttpExchange
from src.activities.reporting.exporter import export_markdown, export_hackerone, export_bugcrowd

router = APIRouter(prefix="/findings", tags=["findings"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PIPELINE_COLUMNS = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("triaged", "Triaged"),
    ("resolved", "Resolved"),
    ("paid", "Paid"),
    ("duplicate", "Duplicate"),
    ("not_applicable", "N/A"),
]


@router.get("", response_class=HTMLResponse)
async def findings_pipeline(request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        findings = session.execute(
            select(Finding).order_by(Finding.created_at.desc())
        ).scalars().all()

        programs = {str(p.id): p for p in session.execute(select(Program)).scalars().all()}

        by_status = {status: [] for status, _ in PIPELINE_COLUMNS}
        for f in findings:
            status_key = f.status.value if f.status else "draft"
            if status_key in by_status:
                by_status[status_key].append({"finding": f, "program": programs.get(str(f.program_id))})

    return templates.TemplateResponse("findings/pipeline.html", {
        "request": request,
        "api_key": api_key,
        "columns": PIPELINE_COLUMNS,
        "by_status": by_status,
        "active": "findings",
    })


@router.get("/{finding_id}", response_class=HTMLResponse)
async def finding_detail(finding_id: str, request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return HTMLResponse("Finding not found", status_code=404)
        program = session.get(Program, str(finding.program_id))
        outcomes = session.execute(
            select(Outcome).where(Outcome.finding_id == finding_id)
            .order_by(Outcome.recorded_at.desc())
        ).scalars().all()

        # Evidence attached to this finding — uses the SAME predicate the exporter
        # uses (finding_id + is_evidence) so the UI never implies something will be
        # exported when it won't.
        evidence = [
            {"id": str(e.id), "method": e.request_method, "url": e.request_url,
             "status": e.response_status, "label": e.label}
            for e in session.execute(
                select(HttpExchange)
                .where(HttpExchange.finding_id == finding_id,
                       HttpExchange.is_evidence.is_(True))
                .order_by(HttpExchange.created_at)
            ).scalars().all()
        ]
        # Unattached exchanges you can add — scoped to the finding's asset when it
        # has one, so evidence from a different asset can't be attached by mistake.
        avail_q = (
            select(HttpExchange)
            .where(HttpExchange.program_id == finding.program_id,
                   HttpExchange.finding_id.is_(None))
        )
        if finding.asset_id is not None:
            avail_q = avail_q.where(HttpExchange.asset_id == finding.asset_id)
        available = [
            {"id": str(e.id), "method": e.request_method, "url": e.request_url,
             "status": e.response_status, "label": e.label}
            for e in session.execute(
                avail_q.order_by(HttpExchange.created_at.desc()).limit(50)
            ).scalars().all()
        ]

    return templates.TemplateResponse("findings/detail.html", {
        "request": request,
        "api_key": api_key,
        "finding": finding,
        "program": program,
        "outcomes": outcomes,
        "evidence": evidence,
        "available_evidence": available,
        "statuses": [s for s, _ in PIPELINE_COLUMNS],
        "outcome_results": ["accepted", "duplicate", "informative", "not_applicable", "paid"],
        "active": "findings",
    })


@router.post("/{finding_id}/evidence/attach")
async def attach_evidence(
    finding_id: uuid.UUID,
    request: Request,
    exchange_id: uuid.UUID = Form(...),
    api_key: str = Depends(verify_api_key),
):
    """Attach a Repeater exchange to this finding as evidence.

    Requires the same program, and the same asset when the finding is tied to one,
    so evidence from a different asset cannot end up in the report. UUID-typed
    params make malformed IDs a 422, not a 500.
    """
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return HTMLResponse("Finding not found", status_code=404)
        ex = session.get(HttpExchange, exchange_id)
        if (ex and str(ex.program_id) == str(finding.program_id)
                and (finding.asset_id is None or str(ex.asset_id) == str(finding.asset_id))):
            ex.finding_id = finding.id
            ex.is_evidence = True
            session.commit()
    # finding_id is already a validated UUID (FastAPI typing); the re-wrap is the
    # sanitizer Snyk recognizes and cannot raise here.
    return RedirectResponse(url=f"/findings/{uuid.UUID(str(finding_id))}", status_code=303)


@router.post("/{finding_id}/evidence/{exchange_id}/detach")
async def detach_evidence(
    finding_id: uuid.UUID,
    exchange_id: uuid.UUID,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """Remove an exchange from this finding's evidence."""
    with Session(engine) as session:
        ex = session.get(HttpExchange, exchange_id)
        if ex and str(ex.finding_id) == str(finding_id):
            ex.finding_id = None
            ex.is_evidence = False
            session.commit()
    return RedirectResponse(url=f"/findings/{uuid.UUID(str(finding_id))}", status_code=303)


@router.post("/{finding_id}/report")
async def update_report(
    finding_id: str,
    request: Request,
    summary: str = Form(""),
    vulnerability_details: str = Form(""),
    steps_to_reproduce: str = Form(""),
    impact: str = Form(""),
    recommended_fix: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return HTMLResponse("Finding not found", status_code=404)
        finding.summary = summary.strip() or None
        finding.vulnerability_details = vulnerability_details.strip() or None
        finding.steps_to_reproduce = steps_to_reproduce.strip() or None
        finding.impact = impact.strip() or None
        finding.recommended_fix = recommended_fix.strip() or None
        session.commit()
        safe_id = str(finding.id)
    return RedirectResponse(url=f"/findings/{uuid.UUID(str(safe_id))}", status_code=303)


@router.post("/{finding_id}/outcome")
async def record_outcome(
    finding_id: str,
    request: Request,
    result: str = Form(...),
    payout_amount: str = Form(""),
    time_spent_hours: str = Form(""),
    lessons: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return HTMLResponse("Finding not found", status_code=404)

        try:
            payout_float = float(payout_amount) if payout_amount.strip() else None
        except ValueError:
            payout_float = None
        try:
            hours_float = float(time_spent_hours) if time_spent_hours.strip() else None
        except ValueError:
            hours_float = None

        outcome = Outcome(
            finding_id=finding_id,
            result=result,
            payout_amount=payout_float,
            time_spent_hours=hours_float,
            lessons=lessons.strip() or None,
        )
        session.add(outcome)

        # Mirror payout to finding if paid
        if result == "paid" and payout_float is not None:
            finding.payout_amount = payout_float
            finding.status = FindingStatus.paid
            finding.paid_at = datetime.now(timezone.utc)

        session.commit()
        safe_id = str(finding.id)

    return RedirectResponse(url=f"/findings/{uuid.UUID(str(safe_id))}", status_code=303)


@router.post("/{finding_id}/status")
async def update_finding_status(
    finding_id: str,
    request: Request,
    new_status: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    try:
        status = FindingStatus[new_status]
    except KeyError:
        return HTMLResponse("Invalid status", status_code=400)

    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return HTMLResponse("Finding not found", status_code=404)

        finding.status = status
        now = datetime.now(timezone.utc)
        if new_status == "submitted":
            finding.submitted_at = now
        elif new_status == "triaged":
            finding.triaged_at = now
        elif new_status in ("resolved", "duplicate", "not_applicable", "paid"):
            finding.resolved_at = now
        if new_status == "paid":
            finding.paid_at = now

        workflow_id = finding.temporal_workflow_id
        session.commit()

    if workflow_id and request.app.state.temporal:
        try:
            handle = request.app.state.temporal.get_workflow_handle(workflow_id)
            await handle.signal("update_status", new_status)
        except Exception:
            pass

    return RedirectResponse(url="/findings", status_code=303)


@router.get("/{finding_id}/export", response_class=PlainTextResponse)
async def export_finding(
    finding_id: str,
    request: Request,
    fmt: str = Query("markdown", pattern="^(markdown|hackerone|bugcrowd)$"),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return PlainTextResponse("Finding not found", status_code=404)
        program = session.get(Program, str(finding.program_id))
        asset = session.get(Asset, str(finding.asset_id)) if finding.asset_id else None
        evidence = session.execute(
            select(HttpExchange)
            .where(HttpExchange.finding_id == finding_id, HttpExchange.is_evidence.is_(True))
            .order_by(HttpExchange.created_at)
        ).scalars().all()

    exporters = {
        "markdown": export_markdown,
        "hackerone": export_hackerone,
        "bugcrowd": export_bugcrowd,
    }
    content = exporters[fmt](finding, program, asset, evidence)
    filename = f"{finding.title[:40].replace(' ', '_').lower()}_{fmt}.md"

    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
