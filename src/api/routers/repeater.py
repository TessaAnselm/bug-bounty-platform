"""
Repeater — send HTTP requests to in-scope assets through the platform.

Every send is guarded before it leaves the host:
  1. method + scheme allowlist
  2. SSRF guard (no private/loopback/link-local targets)
  3. scope validation (validate_target) — refuses out-of-scope hosts
  4. compliance: per-program rate limit + required identifying header
  5. no auto-redirect (3xx surfaced, never auto-chased to an OOS host)
Each exchange is stored for evidence and MCP/AI review.
"""
import time
import uuid
import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.api.auth import verify_api_key
from src.db.session import engine
from src.db.models import HuntSession, Program, HttpExchange, Finding, Severity, FindingStatus
from src.activities.storage.scope import validate_target
from src.lib.compliance import (
    compliance_headers,
    min_send_interval,
    host_from_url,
    is_blocked_host,
    redact_headers,
)

router = APIRouter(prefix="/repeater", tags=["repeater"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

_MAX_BODY = 512 * 1024  # cap stored response body to keep rows small
_MAX_REQUEST_BODY = 256 * 1024
_MAX_REQUEST_HEADERS = 32 * 1024
_DEFAULT_RPS = 3        # fallback rate when a program sets no cap
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_BLOCKED_REQUEST_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "proxy-authorization"}
_TIMEOUT = 15.0

# In-memory per-program throttle: program_id -> monotonic time of last send.
# Resets on restart; a courtesy throttle on top of the human click rate.
_last_send: dict[str, float] = {}


def _parse_headers(raw: str) -> dict:
    headers: dict[str, str] = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip():
            headers[k.strip()] = v.strip()
    return headers


def _blocked_header_names(headers: dict) -> list[str]:
    return sorted(k for k in headers if k.lower() in _BLOCKED_REQUEST_HEADERS)


def _headers_to_text(headers: dict | None) -> str:
    return "\n".join(f"{k}: {v}" for k, v in (headers or {}).items())


def _exchange_dict(ex: HttpExchange) -> dict:
    return {
        "id": str(ex.id),
        "method": ex.request_method,
        "url": ex.request_url,
        "status": ex.response_status,
        "time_ms": ex.response_time_ms,
        "label": ex.label,
        "created_at": ex.created_at,
    }


def _load_history(s: Session, session_id: str) -> list[dict]:
    rows = s.execute(
        select(HttpExchange)
        .where(HttpExchange.hunt_session_id == session_id)
        .order_by(HttpExchange.created_at.desc())
        .limit(50)
    ).scalars().all()
    return [_exchange_dict(e) for e in rows]


def _load_findings(s: Session, program_id: str) -> list[dict]:
    rows = s.execute(
        select(Finding)
        .where(Finding.program_id == program_id)
        .order_by(Finding.created_at.desc())
    ).scalars().all()
    return [{"id": str(f.id), "title": f.title} for f in rows]


def _render(request, session_id, program_info, history, *, form, response=None, error=None, findings=None, api_key=""):
    return templates.TemplateResponse("repeater/index.html", {
        "request": request,
        "api_key": api_key,
        "active": "hunt",
        "session_id": session_id,
        "program": program_info,
        "history": history,
        "form": form,
        "response": response,
        "error": error,
        "findings": findings or [],
    })


@router.get("", response_class=HTMLResponse)
async def repeater_page(
    request: Request,
    session: str,
    from_id: str = "",
    api_key: str = Depends(verify_api_key),
):
    with Session(engine) as s:
        hunt = s.get(HuntSession, session)
        if not hunt:
            return HTMLResponse("Hunt session not found", status_code=404)
        program = s.get(Program, hunt.program_id)
        program_info = {"id": str(program.id), "name": program.name, "platform": program.platform or ""}
        history = _load_history(s, session)
        findings = _load_findings(s, str(program.id))
        form = {"method": "GET", "url": "", "headers": "", "body": "", "label": ""}
        if from_id:
            ex = s.get(HttpExchange, from_id)
            if ex and str(ex.hunt_session_id) == session:
                form = {
                    "method": ex.request_method,
                    "url": ex.request_url,
                    "headers": _headers_to_text(ex.request_headers),
                    "body": ex.request_body or "",
                    "label": ex.label or "",
                }
        return _render(request, session, program_info, history, form=form, findings=findings, api_key=api_key)


@router.post("/send", response_class=HTMLResponse)
async def send_request(
    request: Request,
    hunt_session_id: str = Form(...),
    method: str = Form("GET"),
    url: str = Form(...),
    headers: str = Form(""),
    body: str = Form(""),
    label: str = Form(""),
    api_key: str = Depends(verify_api_key),
):
    method = method.strip().upper()
    url = url.strip()

    # Load program context, then release the DB session before any network I/O.
    with Session(engine) as s:
        hunt = s.get(HuntSession, hunt_session_id)
        if not hunt:
            return HTMLResponse("Hunt session not found", status_code=404)
        program = s.get(Program, hunt.program_id)
        prog_id = str(program.id)
        prog_name = program.name
        platform = program.platform or ""
        scope = program.scope or []
        oos = program.out_of_scope or []
        constraints = program.constraints or {}
        asset_id = str(hunt.asset_id) if hunt.asset_id else None

    form = {"method": method, "url": url, "headers": headers, "body": body, "label": label}
    program_info = {"id": prog_id, "name": prog_name, "platform": platform}

    def render(resp=None, error=None):
        with Session(engine) as s:
            history = _load_history(s, hunt_session_id)
            findings = _load_findings(s, prog_id)
        return _render(request, hunt_session_id, program_info, history, form=form, response=resp, error=error, findings=findings, api_key=api_key)

    # --- guards (fail before any request leaves the host) ---
    if method not in _ALLOWED_METHODS:
        return render(error=f"Method {method} not allowed.")
    if urlparse(url).scheme not in ("http", "https"):
        return render(error="URL must start with http:// or https://")
    if len(headers.encode()) > _MAX_REQUEST_HEADERS:
        return render(error=f"Headers are too large. Limit is {_MAX_REQUEST_HEADERS} bytes.")
    if len(body.encode()) > _MAX_REQUEST_BODY:
        return render(error=f"Request body is too large. Limit is {_MAX_REQUEST_BODY} bytes.")
    host = host_from_url(url)
    if is_blocked_host(host):
        return render(error=f"Blocked: '{host}' is missing or resolves to a private/loopback address (SSRF guard).")
    if not validate_target(host, scope, oos):
        return render(error=f"'{host}' is out of scope for {prog_name} — refusing to send.")

    req_headers = _parse_headers(headers)
    blocked_headers = _blocked_header_names(req_headers)
    if blocked_headers:
        return render(error=f"Blocked request header(s): {', '.join(blocked_headers)}")

    # --- compliance: per-program rate limit + required headers ---
    interval = min_send_interval(constraints, _DEFAULT_RPS)
    wait = interval - (time.monotonic() - _last_send.get(prog_id, 0.0))
    if wait > 0:
        await asyncio.sleep(wait)
    _last_send[prog_id] = time.monotonic()

    required_headers = compliance_headers(platform)
    if platform == "hackerone" and not required_headers:
        return render(error="HackerOne requests require HACKERONE_RESEARCH_USERNAME to be configured.")
    for k, v in required_headers.items():
        req_headers[k] = v

    # --- send (no auto-redirect; surface 3xx instead of chasing it) ---
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(follow_redirects=False, timeout=_TIMEOUT, trust_env=False) as client:
            r = await client.request(
                method, url,
                headers=req_headers,
                content=body.encode() if body else None,
            )
        elapsed = int((time.monotonic() - t0) * 1000)
        resp_status = r.status_code
        resp_headers = dict(r.headers)
        resp_body = r.text[:_MAX_BODY]
    except Exception as e:
        return render(error=f"Request failed: {type(e).__name__}: {e}")

    # --- persist the exchange ---
    with Session(engine) as s:
        ex = HttpExchange(
            hunt_session_id=hunt_session_id,
            program_id=prog_id,
            asset_id=asset_id,
            request_method=method,
            request_url=url,
            request_headers=req_headers,
            request_body=body or None,
            response_status=resp_status,
            response_headers=resp_headers,
            response_body=resp_body,
            response_time_ms=elapsed,
            label=label.strip() or None,
        )
        s.add(ex)
        s.commit()
        s.refresh(ex)
        ex_id = str(ex.id)

    return render(resp={
        "status": resp_status,
        "time_ms": elapsed,
        "headers": redact_headers(resp_headers),
        "body": resp_body,
        "exchange_id": ex_id,
    })


@router.post("/attach", response_class=HTMLResponse)
async def attach_to_finding(
    request: Request,
    hunt_session_id: str = Form(...),
    exchange_id: str = Form(...),
    finding_id: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    """Attach an exchange to an existing finding as evidence (same program only)."""
    target = None
    with Session(engine) as s:
        ex = s.get(HttpExchange, exchange_id)
        finding = s.get(Finding, finding_id)
        if ex and finding and str(ex.program_id) == str(finding.program_id):
            ex.finding_id = finding.id
            ex.is_evidence = True
            s.commit()
            target = str(finding.id)
    if target:
        return RedirectResponse(url=f"/findings/{uuid.UUID(target)}", status_code=303)
    return RedirectResponse(url=f"/repeater?session={uuid.UUID(hunt_session_id)}", status_code=303)


@router.post("/new-finding", response_class=HTMLResponse)
async def new_finding_from_exchange(
    request: Request,
    hunt_session_id: str = Form(...),
    exchange_id: str = Form(...),
    api_key: str = Depends(verify_api_key),
):
    """Create a draft finding seeded from this request and attach it as evidence."""
    fid = None
    with Session(engine) as s:
        ex = s.get(HttpExchange, exchange_id)
        if ex:
            finding = Finding(
                program_id=ex.program_id,
                asset_id=ex.asset_id,
                title=f"{ex.request_method} {ex.request_url}"[:120],
                vuln_type="(set vuln type)",
                severity=Severity.medium,
                status=FindingStatus.draft,
            )
            s.add(finding)
            s.flush()
            ex.finding_id = finding.id
            ex.is_evidence = True
            s.commit()
            fid = str(finding.id)
    if fid:
        return RedirectResponse(url=f"/findings/{uuid.UUID(fid)}", status_code=303)
    return RedirectResponse(url=f"/repeater?session={uuid.UUID(hunt_session_id)}", status_code=303)
