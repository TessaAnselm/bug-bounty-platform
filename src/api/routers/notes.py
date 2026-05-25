from pathlib import Path
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import SessionNote

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("")
async def create_note(
    request: Request,
    program_id: str = Form(...),
    asset_id: Optional[str] = Form(None),
    content: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        note = SessionNote(
            program_id=program_id,
            asset_id=asset_id if asset_id else None,
            content=content,
        )
        session.add(note)
        session.commit()
    return RedirectResponse(url=f"/assets?api_key={api_key}", status_code=303)


@router.post("/{note_id}/delete")
async def delete_note(
    note_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        note = session.get(SessionNote, note_id)
        if note:
            session.delete(note)
            session.commit()
    return RedirectResponse(url=f"/assets?api_key={api_key}", status_code=303)
