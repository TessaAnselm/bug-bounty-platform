import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import Program, ProgramScore


def _score_dict(p: Program, s: ProgramScore) -> dict:
    return {
        "program_id": str(p.id),
        "program_name": p.name,
        "platform": p.platform,
        "total_score": s.total_score,
        "payout_score": s.payout_score,
        "scope_score": s.scope_score,
        "competition_score": s.competition_score,
        "fit_score": s.fit_score,
        "momentum_score": s.momentum_score,
        "top_signals": s.top_signals,
        "scored_at": s.scored_at.isoformat() if s.scored_at else None,
        "scoring_version": s.scoring_version,
    }


def get_ranked_programs() -> str:
    with Session(engine) as session:
        programs = session.execute(select(Program)).scalars().all()
        results = []
        for p in programs:
            score = session.execute(
                select(ProgramScore)
                .where(ProgramScore.program_id == p.id)
                .order_by(ProgramScore.scored_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if score:
                results.append(_score_dict(p, score))

        results.sort(key=lambda x: x["total_score"], reverse=True)
        return json.dumps(results, indent=2)


def get_program_score(program_id: str) -> str:
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return json.dumps({"error": f"Program {program_id} not found"})

        score = session.execute(
            select(ProgramScore)
            .where(ProgramScore.program_id == program_id)
            .order_by(ProgramScore.scored_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not score:
            return json.dumps({"error": f"No score found for program {program_id}"})

        return json.dumps(_score_dict(program, score), indent=2)
