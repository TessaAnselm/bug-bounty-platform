from pathlib import Path
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Alert, Program

router = APIRouter(prefix="/alerts", tags=["alerts"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def alert_list(request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        alerts = session.execute(
            select(Alert).order_by(Alert.seen.asc(), Alert.created_at.desc())
        ).scalars().all()
        programs = {str(p.id): p for p in session.execute(select(Program)).scalars().all()}

    return templates.TemplateResponse("alerts/index.html", {
        "request": request,
        "api_key": api_key,
        "alerts": alerts,
        "programs": programs,
        "active": "alerts",
    })


@router.post("/{alert_id}/seen")
async def mark_seen(alert_id: str, request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        alert = session.get(Alert, alert_id)
        if alert:
            alert.seen = True
            session.commit()
    return RedirectResponse(url="/alerts", status_code=303)


@router.post("/seen-all")
async def mark_all_seen(request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        session.execute(
            Alert.__table__.update().where(Alert.seen == False).values(seen=True)
        )
        session.commit()
    return RedirectResponse(url="/alerts", status_code=303)
