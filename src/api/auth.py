import hashlib
import hmac
import os
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

_API_KEY_HASH = os.getenv("DASHBOARD_API_KEY", "")

# Cookie name used to persist the session across requests
SESSION_COOKIE = "bounty_session"


def verify_api_key(request: Request) -> str:
    """
    Resolve the API key from cookie, header, or query param — in that priority order.

    Cookie is checked first so browser sessions work without ?api_key= in every URL.
    Header (X-API-Key) and query param remain as fallbacks for curl / programmatic access.
    """
    key = (
        request.cookies.get(SESSION_COOKIE)
        or request.headers.get("X-API-Key")
        or request.query_params.get("api_key")
    )
    if not key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    if not hmac.compare_digest(key_hash, _API_KEY_HASH):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return key
