from pathlib import Path
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import ReconRun, Program

router = APIRouter(prefix="/dashboard/health", tags=["health"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def health_view(request: Request, api_key: str = Depends(verify_api_key)):
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    with Session(engine) as session:
        runs = session.execute(
            select(ReconRun)
            .where(ReconRun.started_at >= cutoff)
            .order_by(ReconRun.started_at.desc())
        ).scalars().all()

        programs = {str(p.id): p for p in session.execute(select(Program)).scalars().all()}

        enriched = []
        for r in runs:
            duration = None
            if r.completed_at and r.started_at:
                delta = r.completed_at - r.started_at
                duration = int(delta.total_seconds())
            enriched.append({
                "run": r,
                "program": programs.get(str(r.program_id)),
                "duration_s": duration,
            })

    return templates.TemplateResponse("health/index.html", {
        "request": request,
        "api_key": api_key,
        "runs": enriched,
    })
