from pathlib import Path
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Asset, Program, HuntSession, HuntStatus
from src.activities.checklists.engine import checklists_for_tags, load_checklists_for_session

router = APIRouter(prefix="/hunt", tags=["hunt"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def hunt_list(request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        sessions = session.execute(
            select(HuntSession).order_by(HuntSession.started_at.desc())
        ).scalars().all()

        enriched = []
        for s in sessions:
            asset = session.get(Asset, s.asset_id)
            program = session.get(Program, s.program_id)
            enriched.append({"session": s, "asset": asset, "program": program})

    return templates.TemplateResponse("hunt/index.html", {
        "request": request,
        "api_key": api_key,
        "active": "hunt",
        "sessions": enriched,
    })


@router.post("/start")
async def start_session(
    request: Request,
    asset_id: str = Form(...),
    hypothesis: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    """Start a new hunt session from the triage queue."""
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if not asset:
            return HTMLResponse("Asset not found", status_code=404)

        # Auto-select checklists based on asset tags
        checklists = checklists_for_tags(asset.tags or [])

        hunt = HuntSession(
            program_id=asset.program_id,
            asset_id=asset_id,
            hypothesis=hypothesis.strip() or None,
            status=HuntStatus.active,
            checklists_used=checklists,
            checklist_progress={},
            notes="",
        )
        session.add(hunt)
        session.commit()
        session.refresh(hunt)
        hunt_id = str(hunt.id)

    return RedirectResponse(url=f"/hunt/{uuid.UUID(str(hunt_id))}", status_code=303)


@router.get("/{session_id}", response_class=HTMLResponse)
async def hunt_detail(
    session_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        hunt = session.get(HuntSession, session_id)
        if not hunt:
            return HTMLResponse("Session not found", status_code=404)

        asset = session.get(Asset, hunt.asset_id)
        program = session.get(Program, hunt.program_id)

        checklists = load_checklists_for_session(
            hunt.checklists_used or [],
            hunt.checklist_progress or {},
        )

    return templates.TemplateResponse("hunt/session.html", {
        "request": request,
        "api_key": api_key,
        "active": "hunt",
        "hunt": hunt,
        "asset": asset,
        "program": program,
        "checklists": checklists,
        "statuses": [s.value for s in HuntStatus],
    })


@router.post("/{session_id}/notes")
async def update_notes(
    session_id: str,
    request: Request,
    notes: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        hunt = session.get(HuntSession, session_id)
        if not hunt:
            return HTMLResponse("Session not found", status_code=404)
        hunt.notes = notes
        session.commit()
        safe_id = str(hunt.id)
    return RedirectResponse(url=f"/hunt/{uuid.UUID(str(safe_id))}", status_code=303)


@router.post("/{session_id}/checklist")
async def save_checklist(
    session_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """
    Receives checked item form fields and saves progress.
    Field names use pattern: check_{slug}_{index}
    """
    form = await request.form()

    with Session(engine) as session:
        hunt = session.get(HuntSession, session_id)
        if not hunt:
            return HTMLResponse("Session not found", status_code=404)

        # Rebuild progress dict from submitted checkboxes
        progress: dict[str, list[int]] = {slug: [] for slug in (hunt.checklists_used or [])}
        for key in form.keys():
            if key.startswith("check_"):
                parts = key.split("_", 2)
                if len(parts) == 3:
                    slug = parts[1]
                    try:
                        idx = int(parts[2])
                        if slug in progress:
                            progress[slug].append(idx)
                    except ValueError:
                        pass

        hunt.checklist_progress = progress
        session.commit()
        safe_id = str(hunt.id)

    return RedirectResponse(url=f"/hunt/{uuid.UUID(str(safe_id))}", status_code=303)


@router.post("/{session_id}/status")
async def update_status(
    session_id: str,
    request: Request,
    new_status: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    try:
        status = HuntStatus[new_status]
    except KeyError:
        return HTMLResponse("Invalid status", status_code=400)

    with Session(engine) as session:
        hunt = session.get(HuntSession, session_id)
        if not hunt:
            return HTMLResponse("Session not found", status_code=404)
        hunt.status = status
        if new_status in ("completed", "abandoned"):
            hunt.ended_at = datetime.now(timezone.utc)
        session.commit()
        safe_id = str(hunt.id)
    return RedirectResponse(url=f"/hunt/{uuid.UUID(str(safe_id))}", status_code=303)
