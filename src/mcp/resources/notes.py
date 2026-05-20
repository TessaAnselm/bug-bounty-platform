import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import SessionNote


def _note_dict(n: SessionNote) -> dict:
    return {
        "id": str(n.id),
        "program_id": str(n.program_id),
        "asset_id": str(n.asset_id) if n.asset_id else None,
        "content": n.content,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def list_notes_for_program(program_id: str) -> str:
    with Session(engine) as session:
        notes = session.execute(
            select(SessionNote)
            .where(SessionNote.program_id == program_id)
            .order_by(SessionNote.created_at.desc())
        ).scalars().all()
        return json.dumps([_note_dict(n) for n in notes], indent=2)


def list_notes_for_asset(asset_id: str) -> str:
    with Session(engine) as session:
        notes = session.execute(
            select(SessionNote)
            .where(SessionNote.asset_id == asset_id)
            .order_by(SessionNote.created_at.desc())
        ).scalars().all()
        return json.dumps([_note_dict(n) for n in notes], indent=2)
