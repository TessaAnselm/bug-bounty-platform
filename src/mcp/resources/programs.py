import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import Program, ProgramScore, ReconRun


def _program_dict(p: Program) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "platform": p.platform,
        "scope": p.scope,
        "out_of_scope": p.out_of_scope,
        "max_payout": p.max_payout,
        "status": p.status.value if p.status else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def list_programs() -> str:
    with Session(engine) as session:
        programs = session.execute(select(Program).order_by(Program.created_at.desc())).scalars().all()
        return json.dumps([_program_dict(p) for p in programs], indent=2)


def get_program(program_id: str) -> str:
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return json.dumps({"error": f"Program {program_id} not found"})

        latest_score = session.execute(
            select(ProgramScore)
            .where(ProgramScore.program_id == program_id)
            .order_by(ProgramScore.scored_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        latest_recon = session.execute(
            select(ReconRun)
            .where(ReconRun.program_id == program_id)
            .order_by(ReconRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        result = _program_dict(program)
        if latest_score:
            result["score"] = {
                "total": latest_score.total_score,
                "payout": latest_score.payout_score,
                "scope": latest_score.scope_score,
                "competition": latest_score.competition_score,
                "fit": latest_score.fit_score,
                "momentum": latest_score.momentum_score,
                "top_signals": latest_score.top_signals,
                "scored_at": latest_score.scored_at.isoformat() if latest_score.scored_at else None,
            }
        if latest_recon:
            result["latest_recon"] = {
                "status": latest_recon.status.value,
                "assets_found": latest_recon.assets_found,
                "new_assets": latest_recon.new_assets,
                "started_at": latest_recon.started_at.isoformat() if latest_recon.started_at else None,
            }

        return json.dumps(result, indent=2)
