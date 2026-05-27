import json
import time
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import Program, ProgramScore, ReconRun, Alert
from src.db.models.program import ProgramStatus

router = APIRouter(prefix="/programs", tags=["programs"])

# ── bounty-targets-data fetch + scoring ──────────────────────────────────────

_BTD_CACHE: dict[str, list] = {}
_BTD_CACHE_TS: float = 0.0
_BTD_TTL = 1800  # 30 min

_BTD_URLS = {
    "h1": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/hackerone_data.json",
    "bc": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/bugcrowd_data.json",
}


def _fetch_btd(platform: str) -> list[dict]:
    global _BTD_CACHE_TS
    now = time.time()
    if now - _BTD_CACHE_TS > _BTD_TTL or platform not in _BTD_CACHE:
        try:
            r = httpx.get(_BTD_URLS[platform], timeout=30, follow_redirects=True)
            r.raise_for_status()
            _BTD_CACHE[platform] = r.json()
            _BTD_CACHE_TS = now
        except Exception:
            pass
    return _BTD_CACHE.get(platform, [])


def _parse_h1(programs: list[dict]) -> list[dict]:
    results = []
    for p in programs:
        if not p.get("offers_bounties"):
            continue
        if p.get("submission_state") not in (None, "open"):
            continue
        scope_items = [
            s["asset_identifier"]
            for s in p.get("targets", {}).get("in_scope", [])
            if s.get("eligible_for_bounty") and s.get("asset_identifier")
        ]
        p["_scope_items"] = scope_items
        p["_platform"] = "hackerone"
        results.append(p)
    return results


def _parse_bc(programs: list[dict]) -> list[dict]:
    results = []
    for p in programs:
        if not p.get("max_payout") and not p.get("bounty"):
            continue
        scope_items = []
        for t in p.get("targets", []):
            if isinstance(t, dict):
                val = t.get("name") or t.get("target") or t.get("asset_identifier") or ""
                if val:
                    scope_items.append(str(val))
            elif isinstance(t, str):
                scope_items.append(t)
        p["_scope_items"] = scope_items
        p["_platform"] = "bugcrowd"
        results.append(p)
    return results


def _btd_payout(program: dict) -> float:
    score = 40.0
    if program.get("managed_program"):
        score += 20.0
    avg = program.get("average_time_to_bounty_awarded")
    if avg:
        if avg < 30:
            score += 25.0
        elif avg < 90:
            score += 15.0
        elif avg < 180:
            score += 5.0
    return min(100.0, score)


def _btd_scope(scope_items: list[str]) -> float:
    if not scope_items:
        return 0.0
    score = min(50.0, len(scope_items) * 4.0)
    joined = " ".join(scope_items).lower()
    if "*" in joined:
        score += 30.0
    types: set[str] = set()
    for s in scope_items:
        sl = s.lower()
        if "." in s:
            types.add("domain")
        if "api" in sl:
            types.add("api")
        if sl.startswith("http"):
            types.add("url")
    score += len(types) * 5.0
    return min(100.0, score)


def _btd_competition(program: dict, scope_count: int) -> float:
    score = 70.0
    if scope_count > 50:
        score -= 30.0
    elif scope_count > 20:
        score -= 15.0
    elif scope_count <= 5:
        score += 10.0
    avg_resp = program.get("average_time_to_first_program_response")
    if avg_resp:
        if avg_resp < 3:
            score -= 10.0
        elif avg_resp > 14:
            score += 10.0
    return min(100.0, max(0.0, score))


def _btd_fit(scope_items: list[str], name: str, phase: int) -> float:
    combined = " ".join(scope_items).lower() + " " + name.lower()
    score = 50.0
    if phase == 1:
        if any(kw in combined for kw in ["api", "rest", "graphql", "grpc", "endpoint"]):
            score += 35.0
        if any(kw in combined for kw in ["oauth", "sso", "auth", "saml", "login"]):
            score += 20.0
        if any(kw in combined for kw in ["aws", "gcp", "azure", "cloud", "s3"]):
            score += 10.0
    elif phase == 2:
        if any(kw in combined for kw in ["oauth", "sso", "auth", "saml", "login", "oidc", "jwt"]):
            score += 35.0
        if any(kw in combined for kw in ["api", "rest", "graphql"]):
            score += 20.0
        if any(kw in combined for kw in ["ai", "ml", "llm"]):
            score += 10.0
    else:
        if any(kw in combined for kw in ["ai", "ml", "llm", "model", "claude", "gpt", "openai", "anthropic"]):
            score += 35.0
        if any(kw in combined for kw in ["api", "rest", "graphql", "grpc"]):
            score += 30.0
        if any(kw in combined for kw in ["oauth", "sso", "auth", "saml", "login"]):
            score += 25.0
        if any(kw in combined for kw in ["aws", "gcp", "azure", "cloud", "s3"]):
            score += 15.0
        if any(kw in combined for kw in ["mobile", "ios", "android"]):
            score += 10.0
        if any(kw in combined for kw in ["ai", "ml", "llm", "anthropic", "openai"]):
            score *= 1.3
    return min(100.0, score)


def _btd_momentum(program: dict) -> float:
    score = 50.0
    eff = program.get("response_efficiency_percentage")
    if eff:
        if eff >= 95:
            score += 20.0
        elif eff >= 80:
            score += 10.0
        elif eff < 60:
            score -= 20.0
    return min(100.0, max(0.0, score))


def _btd_signals(scope_items: list[str], name: str) -> list[str]:
    combined = " ".join(scope_items).lower() + " " + name.lower()
    sigs = []
    if any(kw in combined for kw in ["ai", "ml", "llm", "anthropic", "openai"]):
        sigs.append("AI/LLM")
    if any(kw in combined for kw in ["api", "graphql", "grpc"]):
        sigs.append("API")
    if any(kw in combined for kw in ["oauth", "sso", "auth"]):
        sigs.append("Auth")
    if "*" in " ".join(scope_items):
        sigs.append("Wildcard")
    if any(kw in combined for kw in ["aws", "gcp", "azure", "cloud"]):
        sigs.append("Cloud")
    return sigs


def _btd_score(program: dict, phase: int) -> dict:
    scope_items = program.get("_scope_items", [])
    name = program.get("name", "")
    payout = _btd_payout(program)
    scope = _btd_scope(scope_items)
    comp = _btd_competition(program, len(scope_items))
    fit = _btd_fit(scope_items, name, phase)
    momentum = _btd_momentum(program)
    total = payout * 0.20 + scope * 0.20 + comp * 0.25 + fit * 0.25 + momentum * 0.10
    return {
        "name": name,
        "platform": program.get("_platform", ""),
        "url": program.get("url", ""),
        "managed": bool(program.get("managed_program")),
        "response_days": program.get("average_time_to_first_program_response"),
        "scope_count": len(scope_items),
        "scope_items": scope_items[:50],
        "total_score": round(total, 1),
        "payout_score": round(payout, 1),
        "scope_score": round(scope, 1),
        "competition_score": round(comp, 1),
        "fit_score": round(fit, 1),
        "momentum_score": round(momentum, 1),
        "signals": _btd_signals(scope_items, name),
    }
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def program_list(request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        programs = session.execute(select(Program).order_by(Program.created_at.desc())).scalars().all()

        enriched = []
        for p in programs:
            latest_score = session.execute(
                select(ProgramScore)
                .where(ProgramScore.program_id == p.id)
                .order_by(ProgramScore.scored_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            latest_recon = session.execute(
                select(ReconRun)
                .where(ReconRun.program_id == p.id)
                .order_by(ReconRun.started_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            unseen_alerts = session.execute(
                select(func.count()).where(Alert.program_id == p.id, Alert.seen == False)
            ).scalar_one()

            enriched.append({
                "program": p,
                "score": latest_score,
                "latest_recon": latest_recon,
                "unseen_alerts": unseen_alerts,
            })

        enriched.sort(key=lambda x: (x["score"].total_score if x["score"] else 0), reverse=True)

    return templates.TemplateResponse("programs/index.html", {
        "request": request,
        "api_key": api_key,
        "programs": enriched,
    })


@router.get("/discover", response_class=HTMLResponse)
def discover_programs(
    request: Request,
    phase: int = 1,
    platform: str = "h1",
    top: int = 25,
    api_key: str = Depends(verify_api_key),
):
    platforms = ["h1", "bc"] if platform == "all" else [platform if platform in _BTD_URLS else "h1"]
    all_programs: list[dict] = []
    error = None

    for key in platforms:
        raw = _fetch_btd(key)
        if not raw:
            error = "Could not fetch bounty-targets-data from GitHub. Check your connection."
            break
        parsed = _parse_h1(raw) if key == "h1" else _parse_bc(raw)
        all_programs.extend(parsed)

    top = max(5, min(top, 100))
    ranked: list[dict] = []
    if all_programs:
        ranked = sorted(
            [_btd_score(p, phase) for p in all_programs],
            key=lambda x: x["total_score"],
            reverse=True,
        )[:top]

    return templates.TemplateResponse("programs/discover.html", {
        "request": request,
        "api_key": api_key,
        "active": "discover",
        "ranked": ranked,
        "phase": phase,
        "platform": platform,
        "top": top,
        "error": error,
        "total_fetched": len(all_programs),
    })


@router.post("/discover/onboard", response_class=HTMLResponse)
def onboard_from_discover(
    request: Request,
    name: str = Form(...),
    platform: str = Form(...),
    url: str = Form(""),
    scope_json: str = Form("[]"),
    api_key: str = Depends(verify_api_key),
):
    try:
        scope_items = json.loads(scope_json)
        if not isinstance(scope_items, list):
            scope_items = []
        scope_items = [str(s) for s in scope_items[:100] if s]
    except (json.JSONDecodeError, ValueError):
        scope_items = []

    with Session(engine) as session:
        existing = session.execute(
            select(Program).where(Program.name == name)
        ).scalar_one_or_none()
        if existing:
            return RedirectResponse(
                url=f"/programs/{existing.id}?api_key={quote(api_key, safe='')}",
                status_code=303,
            )

        program = Program(
            name=name,
            platform=platform,
            scope=scope_items,
            out_of_scope=[],
            max_payout=None,
            status=ProgramStatus.active,
        )
        session.add(program)
        session.commit()
        program_id = str(program.id)

    return RedirectResponse(
        url=f"/programs/{program_id}?api_key={quote(api_key, safe='')}",
        status_code=303,
    )


@router.get("/{program_id}", response_class=HTMLResponse)
async def program_detail(program_id: str, request: Request, api_key: str = Depends(verify_api_key)):
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return HTMLResponse("Program not found", status_code=404)

        scores = session.execute(
            select(ProgramScore)
            .where(ProgramScore.program_id == program_id)
            .order_by(ProgramScore.scored_at.desc())
            .limit(5)
        ).scalars().all()

        recon_runs = session.execute(
            select(ReconRun)
            .where(ReconRun.program_id == program_id)
            .order_by(ReconRun.started_at.desc())
            .limit(10)
        ).scalars().all()

    return templates.TemplateResponse("programs/detail.html", {
        "request": request,
        "api_key": api_key,
        "program": program,
        "scores": scores,
        "recon_runs": recon_runs,
        "constraints": program.constraints or {},
    })


@router.post("/{program_id}/constraints")
async def update_constraints(
    program_id: str,
    request: Request,
    notes: str = Form(""),
    rate_limit_rpm: str = Form(""),
    allow_active_scanning: str = Form("off"),
    allowed_tools: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return HTMLResponse("Program not found", status_code=404)

        try:
            rpm = int(rate_limit_rpm) if rate_limit_rpm.strip() else None
        except ValueError:
            rpm = None

        tools = [t.strip() for t in allowed_tools.split(",") if t.strip()] or None

        program.constraints = {
            "notes": notes.strip() or None,
            "rate_limit_rpm": rpm,
            "allow_active_scanning": allow_active_scanning == "on",
            "allowed_tools": tools,
        }
        session.commit()
        safe_id = str(program.id)

    return RedirectResponse(url=f"/programs/{safe_id}?api_key={quote(api_key, safe='')}", status_code=303)
