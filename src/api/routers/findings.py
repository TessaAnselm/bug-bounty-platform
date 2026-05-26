from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Finding, Program, Asset, FindingStatus, Outcome
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

    return templates.TemplateResponse("findings/detail.html", {
        "request": request,
        "api_key": api_key,
        "finding": finding,
        "program": program,
        "outcomes": outcomes,
        "statuses": [s for s, _ in PIPELINE_COLUMNS],
        "outcome_results": ["accepted", "duplicate", "informative", "not_applicable", "paid"],
    })


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
    return RedirectResponse(url=f"/findings/{safe_id}?api_key={quote(api_key, safe='')}", status_code=303)


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

    return RedirectResponse(url=f"/findings/{safe_id}?api_key={quote(api_key, safe='')}", status_code=303)


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

    return RedirectResponse(url=f"/findings?api_key={quote(api_key, safe='')}", status_code=303)


@router.get("/{finding_id}/export", response_class=PlainTextResponse)
async def export_finding(
    finding_id: str,
    request: Request,
    fmt: str = Query("markdown", regex="^(markdown|hackerone|bugcrowd)$"),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return PlainTextResponse("Finding not found", status_code=404)
        program = session.get(Program, str(finding.program_id))
        asset = session.get(Asset, str(finding.asset_id)) if finding.asset_id else None

    exporters = {
        "markdown": export_markdown,
        "hackerone": export_hackerone,
        "bugcrowd": export_bugcrowd,
    }
    content = exporters[fmt](finding, program, asset)
    filename = f"{finding.title[:40].replace(' ', '_').lower()}_{fmt}.md"

    return PlainTextResponse(
        content,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
