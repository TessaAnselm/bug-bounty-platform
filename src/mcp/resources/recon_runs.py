import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import ReconRun


def _run_dict(r: ReconRun) -> dict:
    return {
        "id": str(r.id),
        "program_id": str(r.program_id),
        "status": r.status.value if r.status else None,
        "triggered_by": r.triggered_by,
        "assets_found": r.assets_found,
        "new_assets": r.new_assets,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


def get_latest_recon(program_id: str) -> str:
    with Session(engine) as session:
        run = session.execute(
            select(ReconRun)
            .where(ReconRun.program_id == program_id)
            .order_by(ReconRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not run:
            return json.dumps({"error": f"No recon runs found for program {program_id}"})
        return json.dumps(_run_dict(run), indent=2)


def get_recon_history(program_id: str) -> str:
    with Session(engine) as session:
        runs = session.execute(
            select(ReconRun)
            .where(ReconRun.program_id == program_id)
            .order_by(ReconRun.started_at.desc())
            .limit(10)
        ).scalars().all()
        return json.dumps([_run_dict(r) for r in runs], indent=2)
