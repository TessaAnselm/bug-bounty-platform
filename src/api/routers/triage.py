from pathlib import Path
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Asset, Program, AssetStatus

router = APIRouter(prefix="/triage", tags=["triage"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def triage_queue(
    request: Request,
    api_key: str = Depends(verify_api_key),
    program_id: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    interesting_only: Optional[bool] = Query(None),
    min_score: Optional[int] = Query(None),
):
    with Session(engine) as session:
        q = (
            select(Asset)
            .where(Asset.status == AssetStatus.active)
            .order_by(Asset.risk_score.desc().nullslast(), Asset.first_seen.desc())
        )
        if program_id:
            q = q.where(Asset.program_id == program_id)
        if interesting_only:
            q = q.where(Asset.interesting == True)
        if min_score is not None:
            q = q.where(Asset.risk_score >= min_score)

        assets = session.execute(q).scalars().all()

        # Filter by tag in Python — JSONB contains check
        if tag:
            assets = [a for a in assets if tag in (a.tags or [])]

        programs = session.execute(select(Program)).scalars().all()

        # Collect all unique tags across assets for the filter bar
        all_tags: set[str] = set()
        for a in assets:
            all_tags.update(a.tags or [])

    return templates.TemplateResponse("triage/index.html", {
        "request": request,
        "api_key": api_key,
        "active": "triage",
        "assets": assets,
        "programs": programs,
        "all_tags": sorted(all_tags),
        "filter_program_id": program_id,
        "filter_tag": tag,
        "filter_interesting": interesting_only,
        "filter_min_score": min_score,
    })


@router.post("/{asset_id}/flag")
async def toggle_interesting(
    asset_id: str,
    request: Request,
    api_key: str = Depends(verify_api_key),
):
    """Toggle the interesting flag on an asset."""
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if asset:
            asset.interesting = not asset.interesting
            session.commit()
    return RedirectResponse(url="/triage", status_code=303)


@router.post("/{asset_id}/tags")
async def update_tags(
    asset_id: str,
    request: Request,
    tags: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    """Replace tags on an asset. Accepts comma-separated string."""
    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if asset:
            asset.tags = tag_list
            session.commit()
    return RedirectResponse(url="/triage", status_code=303)
