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
import json
import time
import uuid
import asyncio
import logging
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
    resolve_public_ip,
    redact_headers,
)


class _PinnedTransport(httpx.AsyncHTTPTransport):
    """SSRF/DNS-rebinding-safe transport.

    Resolves and validates the target host, then connects to that exact IP (no
    second, uncontrolled DNS lookup) while keeping the original hostname for the
    Host header and TLS — `sni_hostname` makes the certificate verify against the
    hostname even though the TCP target is the pinned IP. A host that resolves to
    any non-public address (or rebinds between guard and connect) is refused here.
    """
    async def handle_async_request(self, request):
        host = request.url.host
        ip = resolve_public_ip(host)
        if ip is None:
            raise httpx.ConnectError(f"blocked or unresolvable host: {host}")
        request.extensions = {**request.extensions, "sni_hostname": host}
        request.url = request.url.copy_with(host=ip)
        return await super().handle_async_request(request)

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

# Audit log — records blocked requests (with reason), not just successful sends.
logger = logging.getLogger("bountyos.repeater")


def _compliance_info(platform: str, scope, oos, constraints) -> dict:
    """Compliance state shown in the Repeater banner so the hunter can see, at a
    glance, the boundaries every request will be held to."""
    constraints = constraints or {}
    return {
        "platform": platform,
        "scope_count": len(scope or []),
        "oos_count": len(oos or []),
        "rate_rpm": constraints.get("rate_limit_rpm"),
        "active_scanning": bool(constraints.get("allow_active_scanning")),
        "header_required": platform == "hackerone",
        "header_ok": not (platform == "hackerone" and not compliance_headers(platform)),
    }


def _parse_headers(raw: str) -> dict:
    """Parse the headers textarea ("Key: Value" per line) into a dict, skipping
    blank or malformed lines."""
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
    """Return any user-supplied headers we refuse to send (Host, Content-Length,
    Transfer-Encoding, Connection, Proxy-Authorization) — the client controls
    these and letting them through enables request smuggling."""
    return sorted(k for k in headers if k.lower() in _BLOCKED_REQUEST_HEADERS)


def _headers_to_text(headers: dict | None) -> str:
    """Render a headers dict back into "Key: Value" lines for the editor textarea."""
    return "\n".join(f"{k}: {v}" for k, v in (headers or {}).items())


def _pretty_body(body: str, headers: dict | None) -> str | None:
    """Indented JSON view of the response body when it parses as JSON, else None.

    Powers the Repeater's "Pretty" toggle — API responses (Deriv's are JSON) are
    far easier to read formatted. Returns None for non-JSON (HTML shells, etc.),
    so the panel falls back to the raw view.
    """
    if not body:
        return None
    ctype = next((v for k, v in (headers or {}).items() if k.lower() == "content-type"), "")
    if "json" not in ctype.lower() and body.lstrip()[:1] not in ("{", "["):
        return None
    try:
        return json.dumps(json.loads(body), indent=2, ensure_ascii=False)
    except (ValueError, TypeError):
        return None


def _exchange_dict(ex: HttpExchange) -> dict:
    """Summarize an exchange for the history table (no request/response bodies)."""
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
    """The 50 most recent exchanges for this hunt session, newest first."""
    rows = s.execute(
        select(HttpExchange)
        .where(HttpExchange.hunt_session_id == session_id)
        .order_by(HttpExchange.created_at.desc())
        .limit(50)
    ).scalars().all()
    return [_exchange_dict(e) for e in rows]


def _load_findings(s: Session, program_id: str, asset_id=None) -> list[dict]:
    """Findings for the 'attach to finding' dropdown — restricted to the given
    asset (or asset-less findings) when asset_id is provided."""
    q = select(Finding).where(Finding.program_id == program_id)
    if asset_id:
        # Only offer findings for this asset (or asset-less ones), so a request
        # can't be attached to a finding belonging to a different asset.
        q = q.where((Finding.asset_id == asset_id) | (Finding.asset_id.is_(None)))
    rows = s.execute(q.order_by(Finding.created_at.desc())).scalars().all()
    return [{"id": str(f.id), "title": f.title} for f in rows]


def _render(request, session_id, program_info, history, *, form, response=None, error=None, findings=None, compliance=None, api_key=""):
    """Render the Repeater page: request editor, compliance banner, history,
    findings dropdown, and an optional response or error."""
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
        "compliance": compliance or {},
    })


@router.get("", response_class=HTMLResponse)
async def repeater_page(
    request: Request,
    session: str,
    from_id: str = "",
    api_key: str = Depends(verify_api_key),
):
    """Render the Repeater for a hunt session.

    Shows the request editor, compliance banner, and exchange history. With
    ?from_id=<exchange> it pre-fills the editor from a past request so you can
    tweak and resend it.
    """
    with Session(engine) as s:
        hunt = s.get(HuntSession, session)
        if not hunt:
            return HTMLResponse("Hunt session not found", status_code=404)
        program = s.get(Program, hunt.program_id)
        program_info = {"id": str(program.id), "name": program.name, "platform": program.platform or ""}
        compliance = _compliance_info(program.platform or "", program.scope, program.out_of_scope, program.constraints)
        history = _load_history(s, session)
        findings = _load_findings(s, str(program.id), str(hunt.asset_id) if hunt.asset_id else None)
        # Pre-fill the required compliance header so it's visible in the editor
        # and easy to copy into your browser/Burp. It's also force-applied
        # server-side on send, so editing/removing it here can't send a
        # non-compliant request — this is just for visibility/convenience.
        prefilled_headers = _headers_to_text(compliance_headers(program.platform or ""))
        form = {"method": "GET", "url": "", "headers": prefilled_headers, "body": "", "label": ""}
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
        return _render(request, session, program_info, history, form=form, findings=findings, compliance=compliance, api_key=api_key)


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
    """Validate, send one request to an in-scope host, and store the exchange.

    Runs the full guard chain (method/scheme allowlist, header/body size caps,
    SSRF block, scope validation, blocked-header check, required compliance
    header), throttles to the program's rate limit, forces the required headers,
    sends without following redirects, caps the stored response body, and records
    the exchange. Blocked requests are audit-logged via reject() and never leave
    the host.
    """
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
    compliance = _compliance_info(platform, scope, oos, constraints)

    def render(resp=None, error=None):
        with Session(engine) as s:
            history = _load_history(s, hunt_session_id)
            findings = _load_findings(s, prog_id, asset_id)
        return _render(request, hunt_session_id, program_info, history, form=form, response=resp, error=error, findings=findings, compliance=compliance, api_key=api_key)

    def reject(reason: str):
        # Audit every blocked request — the *why*, not just successful sends.
        logger.warning("Repeater BLOCKED | program=%s | %s %s | reason=%s", prog_name, method, url, reason)
        return render(error=reason)

    # --- guards (fail before any request leaves the host) ---
    if method not in _ALLOWED_METHODS:
        return reject(f"Method {method} not allowed.")
    if urlparse(url).scheme not in ("http", "https"):
        return reject("URL must start with http:// or https://")
    if len(headers.encode()) > _MAX_REQUEST_HEADERS:
        return reject(f"Headers are too large. Limit is {_MAX_REQUEST_HEADERS} bytes.")
    if len(body.encode()) > _MAX_REQUEST_BODY:
        return reject(f"Request body is too large. Limit is {_MAX_REQUEST_BODY} bytes.")
    host = host_from_url(url)
    if is_blocked_host(host):
        return reject(f"Blocked: '{host}' is missing or resolves to a private/loopback address (SSRF guard).")
    if not validate_target(host, scope, oos):
        return reject(f"'{host}' is out of scope for {prog_name} — refusing to send.")

    req_headers = _parse_headers(headers)
    blocked_headers = _blocked_header_names(req_headers)
    if blocked_headers:
        return reject(f"Blocked request header(s): {', '.join(blocked_headers)}")

    # --- compliance: validate the required header BEFORE touching throttle state ---
    # A rejected request must not consume the rate-limit slot or trigger a sleep.
    required_headers = compliance_headers(platform)
    if platform == "hackerone" and not required_headers:
        return reject("HackerOne requests require HACKERONE_RESEARCH_USERNAME to be configured.")

    # --- per-program rate limit ---
    interval = min_send_interval(constraints, _DEFAULT_RPS)
    wait = interval - (time.monotonic() - _last_send.get(prog_id, 0.0))
    if wait > 0:
        await asyncio.sleep(wait)
    _last_send[prog_id] = time.monotonic()

    for k, v in required_headers.items():
        req_headers[k] = v

    # --- send (no auto-redirect; surface 3xx instead of chasing it) ---
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(
            transport=_PinnedTransport(trust_env=False),
            follow_redirects=False, timeout=_TIMEOUT, trust_env=False,
        ) as client:
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
        "pretty": _pretty_body(resp_body, resp_headers),
        "size": len(resp_body),
        "exchange_id": ex_id,
    })


@router.post("/attach", response_class=HTMLResponse)
async def attach_to_finding(
    request: Request,
    hunt_session_id: uuid.UUID = Form(...),
    exchange_id: uuid.UUID = Form(...),
    finding_id: uuid.UUID = Form(...),
    api_key: str = Depends(verify_api_key),
):
    """Attach an exchange to an existing finding as evidence.

    Same program, and same asset when the finding is tied to one. UUID-typed
    form fields make malformed IDs a 422, not a 500.
    """
    target = None
    with Session(engine) as s:
        ex = s.get(HttpExchange, exchange_id)
        finding = s.get(Finding, finding_id)
        if (ex and finding and str(ex.program_id) == str(finding.program_id)
                and (finding.asset_id is None or str(ex.asset_id) == str(finding.asset_id))):
            ex.finding_id = finding.id
            ex.is_evidence = True
            s.commit()
            target = finding.id
    # IDs are validated UUIDs (FastAPI typing); re-wrap is Snyk's sanitizer and
    # cannot raise here.
    if target:
        return RedirectResponse(url=f"/findings/{uuid.UUID(str(target))}", status_code=303)
    return RedirectResponse(url=f"/repeater?session={uuid.UUID(str(hunt_session_id))}", status_code=303)


@router.post("/new-finding", response_class=HTMLResponse)
async def new_finding_from_exchange(
    request: Request,
    hunt_session_id: uuid.UUID = Form(...),
    exchange_id: uuid.UUID = Form(...),
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
            fid = finding.id
    if fid:
        return RedirectResponse(url=f"/findings/{uuid.UUID(str(fid))}", status_code=303)
    return RedirectResponse(url=f"/repeater?session={uuid.UUID(str(hunt_session_id))}", status_code=303)
