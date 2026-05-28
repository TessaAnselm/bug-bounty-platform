from pathlib import Path
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import ReconRun, Program, ReconStatus

router = APIRouter(prefix="/dashboard/health", tags=["health"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# A run still marked 'running' after this long means the worker died before it
# could call complete_recon_run or fail_recon_run. Mark it failed automatically
# so the health page always reflects reality without manual DB fixes.
_STALE_AFTER = timedelta(hours=1)


def _reap_stale_runs(session: Session) -> None:
    stale_cutoff = datetime.now(timezone.utc) - _STALE_AFTER
    stale = session.execute(
        select(ReconRun).where(
            ReconRun.status == ReconStatus.running,
            ReconRun.started_at <= stale_cutoff,
        )
    ).scalars().all()
    for run in stale:
        run.status = ReconStatus.failed
        run.completed_at = datetime.now(timezone.utc)
    if stale:
        session.commit()


@router.get("", response_class=HTMLResponse)
async def health_view(request: Request, api_key: str = Depends(verify_api_key)):
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    with Session(engine) as session:
        _reap_stale_runs(session)

        runs = session.execute(
            select(ReconRun)
            .where(ReconRun.started_at >= cutoff)
            .order_by(ReconRun.started_at.desc())
        ).scalars().all()

        programs = {str(p.id): p for p in session.execute(select(Program)).scalars().all()}

        now = datetime.now(timezone.utc)
        enriched = []
        for r in runs:
            duration = None
            if r.completed_at and r.started_at:
                duration = int((r.completed_at - r.started_at).total_seconds())
            elif r.started_at and r.status.value == "running":
                duration = int((now - r.started_at).total_seconds())

            # Infer why a run failed so you don't have to open the worker log.
            cause = None
            if r.status.value == "failed":
                if duration and duration >= 3600:
                    cause = "Worker died — stale run"
                elif duration and duration < 60:
                    cause = "Failed at startup"
                else:
                    cause = "Activity exhausted retries"

            enriched.append({
                "run": r,
                "program": programs.get(str(r.program_id)),
                "duration_s": duration,
                "likely_cause": cause,
            })

    return templates.TemplateResponse("health/index.html", {
        "request": request,
        "api_key": api_key,
        "runs": enriched,
        "active": "health",
    })
