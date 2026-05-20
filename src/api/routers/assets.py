from pathlib import Path
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Asset, Program, SessionNote, Finding

router = APIRouter(prefix="/assets", tags=["assets"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    api_key: str = Depends(verify_api_key),
    program_id: Optional[str] = Query(None),
    is_new: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    asset_type: Optional[str] = Query(None),
):
    with Session(engine) as session:
        q = select(Asset).order_by(Asset.is_new.desc(), Asset.first_seen.desc())
        if program_id:
            q = q.where(Asset.program_id == program_id)
        if is_new is not None:
            q = q.where(Asset.is_new == is_new)
        if status:
            q = q.where(Asset.status.in_([status]))
        if asset_type:
            q = q.where(Asset.type.in_([asset_type]))

        assets = session.execute(q).scalars().all()
        programs = session.execute(select(Program)).scalars().all()

    return templates.TemplateResponse("assets/index.html", {
        "request": request,
        "api_key": api_key,
        "assets": assets,
        "programs": programs,
        "filter_program_id": program_id,
        "filter_is_new": is_new,
        "filter_status": status,
        "filter_type": asset_type,
    })


@router.get("/{asset_id}", response_class=HTMLResponse)
async def asset_detail(asset_id: str, request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if not asset:
            return HTMLResponse("Asset not found", status_code=404)

        program = session.get(Program, str(asset.program_id))

        notes = session.execute(
            select(SessionNote)
            .where(SessionNote.asset_id == asset_id)
            .order_by(SessionNote.created_at.desc())
        ).scalars().all()

        findings = session.execute(
            select(Finding).where(Finding.asset_id == asset_id)
        ).scalars().all()

    return templates.TemplateResponse("assets/detail.html", {
        "request": request,
        "api_key": api_key,
        "asset": asset,
        "program": program,
        "notes": notes,
        "findings": findings,
    })
