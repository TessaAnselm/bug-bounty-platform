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

from src.api.auth import (
    verify_api_key,
    verify_session_token,
    create_session_token,
    key_matches,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
)
from src.api.routers import programs, assets, findings, alerts, notes, health, triage, hunt, repeater

load_dotenv()

BASE_DIR = Path(__file__).parent

# Set COOKIE_SECURE=true once the dashboard is served over HTTPS (e.g. a VPS).
# It stays false for local 127.0.0.1 use because the loopback is plain HTTP and
# a Secure cookie would never be sent.
_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def _set_session_cookie(response) -> None:
    """Attach a fresh signed session-token cookie to a response.

    The cookie value is a signed token, never the raw API key — that is the
    whole point of this auth model (see src/api/auth.py).
    """
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(),
        httponly=True,          # not readable by JS
        samesite="strict",      # not sent on cross-site requests
        secure=_COOKIE_SECURE,  # HTTPS-only when enabled
        max_age=SESSION_MAX_AGE,
        path="/",
    )


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
app.include_router(repeater.router)


@app.middleware("http")
async def auto_login(request: Request, call_next):
    """Convert a valid ?api_key= browser visit into a session cookie.

    Keeps the start.sh "?api_key=KEY" convenience URL working while immediately
    getting the raw key out of the address bar: set the session cookie, then
    redirect to a constant landing page (no request data echoed back). Only HTML
    GET navigations are auto-converted; programmatic clients (no text/html
    Accept) keep using the per-request header/query path in verify_api_key.
    """
    if (
        request.method == "GET"
        and "text/html" in request.headers.get("accept", "")
        and "api_key" in request.query_params
        and not verify_session_token(request.cookies.get(SESSION_COOKIE, ""))
        and key_matches(request.query_params["api_key"])
    ):
        # Redirect to a constant landing page after auto-login. We deliberately
        # do NOT echo any part of the request URL into the redirect, so no
        # request-derived data flows into the Location header (no open redirect
        # possible). The api_key is dropped from the address bar as a result.
        response = RedirectResponse(url="/programs", status_code=303)
        _set_session_cookie(response)
        return response
    return await call_next(request)


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
    if not key_matches(key):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Invalid API key"}
        )
    # Key verified once here; from now on the browser carries a signed session
    # token cookie, never the raw key.
    response = RedirectResponse(url="/programs", status_code=303)
    _set_session_cookie(response)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}
