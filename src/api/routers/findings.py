from pathlib import Path
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Finding, Program, FindingStatus

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

    return templates.TemplateResponse("findings/detail.html", {
        "request": request,
        "api_key": api_key,
        "finding": finding,
        "program": program,
        "statuses": [s for s, _ in PIPELINE_COLUMNS],
    })


@router.post("/{finding_id}/status")
async def update_finding_status(
    finding_id: str,
    request: Request,
    new_status: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            return HTMLResponse("Finding not found", status_code=404)

        finding.status = FindingStatus[new_status]
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

    return RedirectResponse(url=f"/findings?api_key={api_key}", status_code=303)
