"""
Dashboard authentication — session-token model.

Design (why it works this way):
  The dashboard is protected by a single high-entropy API key. Only the
  SHA-256 *hash* of that key is stored (DASHBOARD_API_KEY in .env) — the
  plaintext is never persisted.

  Browsers do NOT carry the raw key around. At login we verify the key once,
  then hand the browser a signed, time-limited *session token* (see
  create_session_token). The cookie holds that token, not the key. This means:
    - the long-lived secret never sits in the cookie jar, URLs, logs, or history
    - a stolen cookie expires after SESSION_MAX_AGE and is not the master key
    - the token is stateless (HMAC-signed) so it survives a dashboard restart
      without a server-side session store

  Programmatic clients (curl, scripts) still authenticate per-request with the
  raw key via the `X-API-Key` header or `?api_key=` query param — they don't
  need a browser session. The auto-login middleware in main.py converts a valid
  `?api_key=` browser visit into a session cookie and strips the key from the URL.
"""
import base64
import hashlib
import hmac
import os
import time
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

# SHA-256 hash of the dashboard API key. Empty if unset → auth fails closed
# (every comparison below rejects, so the dashboard is locked, never open).
_API_KEY_HASH = os.getenv("DASHBOARD_API_KEY", "")

# Cookie that carries the signed session token across requests.
SESSION_COOKIE = "bounty_session"

# How long a browser session stays valid. Enforced server-side in
# verify_session_token (the cookie's own max_age is only a browser hint).
SESSION_MAX_AGE = 86400 * 7  # 7 days

# The key hash doubles as the HMAC signing secret: it is secret, stable across
# restarts, and already loaded. No separate signing key to manage.
_SIGNING_SECRET = _API_KEY_HASH.encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_session_token() -> str:
    """Return a signed token proving a successful login at the current time.

    Format: "<issued_at>.<hmac_sig>" where issued_at is unix seconds and the
    signature is HMAC-SHA256 over the issued_at bytes, keyed by the API-key hash.
    """
    issued_at = str(int(time.time())).encode()
    sig = hmac.new(_SIGNING_SECRET, issued_at, hashlib.sha256).digest()
    return f"{_b64(issued_at)}.{_b64(sig)}"


def verify_session_token(token: str) -> bool:
    """True if token is a well-formed, correctly-signed, non-expired session."""
    if not token or not _API_KEY_HASH:
        return False
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        issued_at_bytes = _unb64(payload_b64)
        sig = _unb64(sig_b64)
    except Exception:
        return False
    expected = hmac.new(_SIGNING_SECRET, issued_at_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        issued_at = int(issued_at_bytes.decode())
    except ValueError:
        return False
    return (time.time() - issued_at) <= SESSION_MAX_AGE


def key_matches(key: str) -> bool:
    """Constant-time check of a raw API key against the stored hash."""
    if not key or not _API_KEY_HASH:
        return False
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return hmac.compare_digest(key_hash, _API_KEY_HASH)


def verify_api_key(request: Request) -> str:
    """FastAPI dependency that authenticates a request, or raises 401.

    Accepts, in priority order:
      1. a valid session-token cookie (browser sessions), or
      2. the raw API key via X-API-Key header or ?api_key= query (programmatic).

    The return value is an opaque marker, not the key — callers must never put it
    into URLs, templates, or logs (that was the old leak this design removes).
    """
    if verify_session_token(request.cookies.get(SESSION_COOKIE, "")):
        return "session"

    raw = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if raw and key_matches(raw):
        return "api-key"

    raise HTTPException(status_code=401, detail="Invalid or missing API key")
