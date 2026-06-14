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


def _is_public(addr: ipaddress._BaseAddress) -> bool:
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def resolve_public_ip(host: str | None) -> str | None:
    """Resolve host and return one public IP to pin the connection to, or None
    if it's missing, unresolvable, or resolves to ANY non-public address.

    Returning a specific IP lets the caller connect to exactly that address with
    no second DNS lookup — closing the DNS-rebinding window. We reject the host
    outright if *any* resolved address is non-public (so a host that mixes a
    public and a private record can't be used at all). IPv4 is preferred.
    """
    if not host:
        return None
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None  # unresolvable → block
    candidates: list[tuple[int, str]] = []
    for info in infos:
        ip_str = info[4][0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return None
        if not _is_public(addr):
            return None  # any non-public address → block the host entirely
        candidates.append((addr.version, ip_str))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])  # IPv4 (4) before IPv6 (6)
    return candidates[0][1]


def is_blocked_host(host: str | None) -> bool:
    """True if host is missing, unresolvable, or resolves to a non-public address.

    SSRF guard for any server-side request feature; blocks loopback, private,
    link-local (incl. cloud metadata 169.254.169.254), reserved, multicast, and
    unspecified addresses. Scope validation runs on top of this. The Repeater
    additionally pins the resolved IP for the connection (see resolve_public_ip)
    so there is no exploitable DNS-rebinding window at send time.
    """
    return resolve_public_ip(host) is None


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
