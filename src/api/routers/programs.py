import json
import re
import time
import uuid
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
# bounty-targets-data is a community-maintained daily snapshot of all public
# HackerOne and Bugcrowd programs. We fetch it once and cache for 30 min so
# the Discover page feels instant without hammering GitHub on every page load.

_BTD_CACHE: dict[str, list] = {}
_BTD_CACHE_TS: float = 0.0
_BTD_TTL = 1800  # 30 min — fresh enough for program selection decisions

_BTD_URLS = {
    "h1": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/hackerone_data.json",
    "bc": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/bugcrowd_data.json",
}


def _fetch_btd(platform: str) -> list[dict]:
    """Fetch raw program list from bounty-targets-data, served from GitHub.
    Results are cached in-process for 30 min to avoid hitting GitHub on every
    Discover page load. Returns an empty list if the fetch fails — the caller
    shows an error banner rather than crashing.
    """
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
    """Filter and normalize HackerOne programs from bounty-targets-data.
    Drops programs that don't pay bounties or have closed submissions.
    Attaches _scope_items (bounty-eligible asset identifiers) and _platform
    so downstream scoring functions don't need to know the source format.
    """
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
    """Filter and normalize Bugcrowd programs from bounty-targets-data.
    Bugcrowd's schema differs from H1 — targets can be dicts or bare strings,
    so we normalize both forms into a flat list of asset identifiers.
    """
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
    """Score 0–100 for payout attractiveness (20% of total).
    Proxy signals: managed program (faster payment pipeline) and average days
    to bounty awarded (time-to-cash predicts whether the program is actively
    triaging rather than sitting on reports).
    """
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
    """Score 0–100 for attack surface breadth (20% of total).
    Wildcard domains (+30) matter most — they mean subdomain enumeration and
    asset discovery are worth doing. Asset type diversity (domain vs API vs URL)
    adds a smaller bonus because mixed-type scope tends to have more logic bugs.
    """
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
    """Score 0–100 for how uncrowded the program is (25% of total).
    Large scope attracts more hunters, so we penalize it. Slow initial response
    is a counter-intuitive positive: it signals that the triage queue isn't
    being dominated by fast-moving top hunters who sweep new reports immediately.
    """
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
    """Score 0–100 for how well the program matches the active hunting phase (25% of total).
    Phase 1 = IDOR/API: boosts REST, GraphQL, gRPC, auth keywords.
    Phase 2 = OAuth/Auth: boosts OAuth, SSO, SAML, OIDC, JWT keywords.
    Phase 3 = AI/LLM: boosts AI/LLM keywords and applies a 1.3x multiplier
    because AI programs are rare and underexplored.
    """
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
    """Score 0–100 for program health and responsiveness (10% of total).
    Response efficiency (% of reports that get a response) is the best
    single signal for whether the security team is actively engaged vs.
    letting reports pile up with no feedback.
    """
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
    """Return short keyword tags shown on the Discover table (AI/LLM, API, Auth, Wildcard, Cloud).
    These are the same signals that drive fit scoring — surfacing them as tags
    lets you quickly eyeball why a program ranked where it did.
    """
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
    """Combine all five dimension scores into a single ranked result dict.
    Weights: payout 20%, scope 20%, competition 25%, fit 25%, momentum 10%.
    Competition and fit carry the most weight because a high-paying program
    with perfect fit is useless if it's overrun by experienced hunters.
    """
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
async def program_list(
    request: Request,
    show_archived: bool = False,
    api_key: str = Depends(verify_api_key),
):
    """Main program dashboard — shows all active and paused programs with scores.
    Archived programs are hidden by default (?show_archived=true to include them).
    Each card is enriched with the latest score, most recent recon run, and
    unseen alert count so you can see program health at a glance.
    """
    with Session(engine) as session:
        q = select(Program).order_by(Program.created_at.desc())
        if not show_archived:
            q = q.where(Program.status != ProgramStatus.archived)
        programs = session.execute(q).scalars().all()

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
        "show_archived": show_archived,
        "active": "programs",
    })


@router.get("/discover", response_class=HTMLResponse)
def discover_programs(
    request: Request,
    phase: int = 1,
    platform: str = "h1",
    top: int = 25,
    api_key: str = Depends(verify_api_key),
):
    """Program discovery page — fetches and scores 230+ programs from bounty-targets-data.
    Filtered and ranked by the 5-dimension scoring model tuned to the selected phase.
    Results are limited to `top` (5–100) and cached for 30 min so repeated page
    loads don't re-fetch from GitHub every time.
    """
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
    url: str = Form(""),  # accepted from the discover form but not stored — Program model has no url column
    scope_json: str = Form("[]"),
    api_key: str = Depends(verify_api_key),
):
    """Create a new program from the Discover page with a single click.
    Deduplicates by name — clicking Onboard twice redirects to the existing record
    rather than creating a duplicate. Scope comes from bounty-targets-data as a
    JSON-encoded list; the detail page scope editor can refine it afterwards.
    """
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
                url=f"/programs/{uuid.UUID(str(existing.id))}",
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
        url=f"/programs/{uuid.UUID(str(program_id))}",
        status_code=303,
    )


@router.get("/{program_id}", response_class=HTMLResponse)
async def program_detail(program_id: str, request: Request, api_key: str = Depends(verify_api_key)):
    """Program detail page — scope, scores, constraints, recon history, and status controls.
    Loads the 5 most recent scores (for trend visibility) and the 10 most recent
    recon runs. Constraints and scope are rendered as editable forms so everything
    about the program can be managed from this single page.
    """
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
        "active": "programs",
    })


@router.post("/{program_id}/constraints")
async def update_constraints(
    program_id: str,
    request: Request,
    notes: str = Form(""),
    rate_limit_rpm: str = Form(""),
    allow_active_scanning: str = Form("of"),
    allowed_tools: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    """Save program constraints — rate limit, active scanning gate, allowed tools, notes.
    Constraints are stored as JSONB and read by ReconWorkflow before any scan starts.
    allow_active_scanning=False means only passive recon runs (subfinder, gau, crt.sh).
    Notes are free-text: use them for program-specific rules like 'no automated scanning
    on *.api.example.com' or hard OOS lines not captured in out_of_scope.
    """
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

    return RedirectResponse(url=f"/programs/{uuid.UUID(str(safe_id))}", status_code=303)


_SAFE_SCOPE_ENTRY = re.compile(r"^[a-zA-Z0-9.\-*/: _]+$")


def _split_scope(text: str) -> tuple[list[str], list[str]]:
    """Split newline-delimited scope textarea into valid and skipped entries.

    Valid: domains, wildcards, URLs. Skipped: product names, descriptions,
    anything with characters that can't be part of a domain or URL pattern.
    Skipped entries are shown as a warning so the user knows they were ignored.
    """
    valid, skipped = [], []
    for line in text.splitlines():
        entry = line.strip()
        if not entry:
            continue
        if _SAFE_SCOPE_ENTRY.match(entry):
            valid.append(entry)
        else:
            skipped.append(entry)
    return valid, skipped


@router.post("/{program_id}/scope")
async def update_scope(
    program_id: str,
    request: Request,
    scope: str = Form(""),
    out_of_scope: str = Form(""),
    max_payout: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    """Update in-scope targets, OOS exclusions, and max payout from the detail page editor.
    Scope and out_of_scope are newline-delimited in the form and stored as JSONB string arrays.
    Entries that contain characters outside domain/URL patterns (e.g. product names like
    'Kong Mesh') are flagged and skipped — they can't be enumerated by subfinder anyway.
    validate_target() in store_assets reads program.scope to enforce boundaries before
    any asset is written to the database.
    """
    scope_valid, scope_skipped = _split_scope(scope)
    oos_valid, oos_skipped = _split_scope(out_of_scope)

    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return HTMLResponse("Program not found", status_code=404)

        program.scope = scope_valid
        program.out_of_scope = oos_valid
        try:
            program.max_payout = int(max_payout) if max_payout.strip() else None
        except ValueError:
            program.max_payout = None
        session.commit()
        safe_id = str(program.id)

    # Pass skipped entries back as a query param so the detail page can show a warning.
    skipped_all = scope_skipped + oos_skipped
    warning = quote(", ".join(skipped_all), safe="") if skipped_all else ""
    url = f"/programs/{uuid.UUID(str(safe_id))}"
    if warning:
        url += f"?scope_warning={warning}"
    return RedirectResponse(url=url, status_code=303)


_VALID_STATUS_TRANSITIONS = {
    ProgramStatus.active: [ProgramStatus.paused, ProgramStatus.archived],
    ProgramStatus.paused: [ProgramStatus.active, ProgramStatus.archived],
    ProgramStatus.archived: [ProgramStatus.active],
}


@router.post("/{program_id}/status")
async def update_status(
    program_id: str,
    request: Request,
    status: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    """Transition a program between active, paused, and archived states.
    Valid transitions are enforced by _VALID_STATUS_TRANSITIONS — you can't jump
    directly from archived to paused, for example. ReconWorkflow checks program.status
    before running and refuses to scan anything that isn't active.
    """
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return HTMLResponse("Program not found", status_code=404)

        try:
            new_status = ProgramStatus(status)
        except ValueError:
            return HTMLResponse("Invalid status", status_code=400)

        allowed = _VALID_STATUS_TRANSITIONS.get(program.status, [])
        if new_status not in allowed:
            return HTMLResponse("Invalid status transition", status_code=400)

        program.status = new_status
        session.commit()
        safe_id = str(program.id)

    return RedirectResponse(url=f"/programs/{uuid.UUID(str(safe_id))}", status_code=303)
