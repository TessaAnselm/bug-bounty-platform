import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from temporalio.client import Client

from src.api.auth import verify_api_key, SESSION_COOKIE, _API_KEY_HASH
from src.api.routers import programs, assets, findings, alerts, notes, health, triage, hunt

import hashlib
import hmac

load_dotenv()

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = os.getenv("TEMPORAL_PORT", "7233")
    try:
        app.state.temporal = await Client.connect(f"{host}:{port}")
    except Exception:
        app.state.temporal = None
    yield


app = FastAPI(title="Bug Bounty Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(programs.router)
app.include_router(assets.router)
app.include_router(findings.router)
app.include_router(alerts.router)
app.include_router(notes.router)
app.include_router(health.router)
app.include_router(triage.router)
app.include_router(hunt.router)


@app.exception_handler(HTTPException)
async def auth_redirect(request: Request, exc: HTTPException):
    """Redirect to login page on 401 instead of returning a bare error response."""
    if exc.status_code == 401:
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(content=exc.detail, status_code=exc.status_code)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(url="/programs")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, key: str = Form(...)):
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    if not hmac.compare_digest(key_hash, _API_KEY_HASH):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid API key"}
        )
    response = RedirectResponse(url="/programs", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=key,
        httponly=True,       # not readable by JS
        samesite="strict",   # no cross-site requests
        max_age=86400 * 7,   # 7-day session
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}
