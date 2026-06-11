"""
Shared recon/testing compliance helpers.

Both the recon probe and the Repeater route requests to live program assets, so
they must apply the same rules: the program's request-rate cap, any required
identifying header, and a guard against ever sending to a non-public address.
Centralizing them here keeps enforcement identical across features.
"""
import ipaddress
import os
import re
import socket
from urllib.parse import urlparse

# HackerOne programs require an identifying header on every request. Set your H1
# username in the environment; we attach it for hackerone-platform programs.
HACKERONE_RESEARCH_USERNAME = os.getenv("HACKERONE_RESEARCH_USERNAME", "").strip()

# Headers we never expose outside the DB (e.g. to the MCP/AI view).
_SENSITIVE_HEADERS = {"cookie", "authorization", "x-api-key", "set-cookie", "proxy-authorization"}

_SECRET_VALUE_PATTERNS = [
    re.compile(
        r'(?i)("?(?:access_token|refresh_token|id_token|api[_-]?key|csrf(?:_token)?|'
        r'authenticity_token|password|passwd|secret|session|token)"?\s*[:=]\s*)'
        r'(["\']?)[^&\s,"\'}]+(\2)'
    ),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+"),
]


def compliance_headers(platform: str) -> dict[str, str]:
    """Headers that must be attached to every request to a given platform's assets."""
    headers: dict[str, str] = {}
    if platform == "hackerone" and HACKERONE_RESEARCH_USERNAME:
        headers["X-HackerOne-Research"] = HACKERONE_RESEARCH_USERNAME
    return headers


def program_rate_rps(constraints: dict | None) -> int | None:
    """Convert a program's stated rate cap (requests/minute) to integer
    requests/second, for tools like httpx whose -rate-limit takes an int.

    Returns None when no cap is set, so the caller can fall back to its default.
    Note: this floors to >=1 rps, so for sub-60-rpm caps prefer
    min_send_interval(), which is exact.
    """
    rpm = (constraints or {}).get("rate_limit_rpm")
    if rpm and rpm > 0:
        return max(1, int(rpm) // 60)
    return None


def min_send_interval(constraints: dict | None, default_rps: float = 3.0) -> float:
    """Exact minimum seconds between requests to honor a program's rate cap.

    Computed straight from requests/minute (60/rpm), so a slow cap like 30/min
    correctly yields a 2s gap instead of being rounded up past the limit.
    """
    rpm = (constraints or {}).get("rate_limit_rpm")
    if rpm and rpm > 0:
        return 60.0 / float(rpm)
    return 1.0 / default_rps


def host_from_url(url: str) -> str | None:
    """Extract the hostname from a URL, or None if it can't be parsed."""
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def is_blocked_host(host: str | None) -> bool:
    """True if host is missing, unresolvable, or resolves to a non-public address.

    This is the SSRF guard for any server-side request feature: it blocks
    loopback, private, link-local (incl. cloud metadata 169.254.169.254),
    reserved, multicast, and unspecified addresses. Scope validation still runs
    on top of this — this is defense-in-depth so the platform can never be used
    to reach internal services even if a scope entry is misconfigured.

    Note: resolution here and at send time is a small TOCTOU window (DNS
    rebinding); acceptable for a single-user local tool, hardened later by
    pinning the resolved IP.
    """
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # unresolvable → block
    for info in infos:
        ip_str = info[4][0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return True
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            return True
    return False


def redact_headers(headers: dict | None) -> dict:
    """Return headers with sensitive values masked — for any view leaving the DB."""
    return {
        k: ("<redacted>" if k.lower() in _SENSITIVE_HEADERS else v)
        for k, v in (headers or {}).items()
    }


def redact_text(text: str | None) -> str | None:
    """Best-effort redaction for request/response bodies before MCP/AI exposure.

    This is intentionally conservative and pattern-based. It will not catch every
    secret shape, but it removes common token/password/API-key forms from JSON,
    form-encoded, and plain text excerpts.
    """
    if text is None:
        return None
    redacted = text
    for pattern in _SECRET_VALUE_PATTERNS:
        redacted = pattern.sub(r"\1<redacted>", redacted)
    return redacted
