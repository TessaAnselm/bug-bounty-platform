import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from temporalio.client import Client

from src.api.routers import programs, assets, findings, alerts, notes, health, triage

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


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    api_key = request.query_params.get("api_key", "")
    return RedirectResponse(url=f"/programs?api_key={api_key}")


@app.get("/health/live")
async def liveness():
    return {"status": "ok"}
