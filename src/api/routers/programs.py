from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Program, ProgramScore, ReconRun, Alert

router = APIRouter(prefix="/programs", tags=["programs"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def program_list(request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        programs = session.execute(select(Program).order_by(Program.created_at.desc())).scalars().all()

        enriched = []
        for p in programs:
            latest_score = session.execute(
                select(ProgramScore)
                .where(ProgramScore.program_id == p.id)
                .order_by(ProgramScore.scored_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            latest_recon = session.execute(
                select(ReconRun)
                .where(ReconRun.program_id == p.id)
                .order_by(ReconRun.started_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            unseen_alerts = session.execute(
                select(func.count()).where(Alert.program_id == p.id, Alert.seen == False)
            ).scalar_one()

            enriched.append({
                "program": p,
                "score": latest_score,
                "latest_recon": latest_recon,
                "unseen_alerts": unseen_alerts,
            })

        enriched.sort(key=lambda x: (x["score"].total_score if x["score"] else 0), reverse=True)

    return templates.TemplateResponse("programs/index.html", {
        "request": request,
        "api_key": api_key,
        "programs": enriched,
    })


@router.get("/{program_id}", response_class=HTMLResponse)
async def program_detail(program_id: str, request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return HTMLResponse("Program not found", status_code=404)

        scores = session.execute(
            select(ProgramScore)
            .where(ProgramScore.program_id == program_id)
            .order_by(ProgramScore.scored_at.desc())
            .limit(5)
        ).scalars().all()

        recon_runs = session.execute(
            select(ReconRun)
            .where(ReconRun.program_id == program_id)
            .order_by(ReconRun.started_at.desc())
            .limit(10)
        ).scalars().all()

    return templates.TemplateResponse("programs/detail.html", {
        "request": request,
        "api_key": api_key,
        "program": program,
        "scores": scores,
        "recon_runs": recon_runs,
        "constraints": program.constraints or {},
    })


@router.post("/{program_id}/constraints")
async def update_constraints(
    program_id: str,
    request: Request,
    notes: str = Form(""),
    rate_limit_rpm: str = Form(""),
    allow_active_scanning: str = Form("off"),
    allowed_tools: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return HTMLResponse("Program not found", status_code=404)

        try:
            rpm = int(rate_limit_rpm) if rate_limit_rpm.strip() else None
        except ValueError:
            rpm = None

        tools = [t.strip() for t in allowed_tools.split(",") if t.strip()] or None

        program.constraints = {
            "notes": notes.strip() or None,
            "rate_limit_rpm": rpm,
            "allow_active_scanning": allow_active_scanning == "on",
            "allowed_tools": tools,
        }
        session.commit()
        safe_id = str(program.id)

    return RedirectResponse(url=f"/programs/{safe_id}?api_key={quote(api_key, safe='')}", status_code=303)
