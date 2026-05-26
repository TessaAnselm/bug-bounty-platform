import hashlib
import hmac
import os
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

_API_KEY_HASH = os.getenv("DASHBOARD_API_KEY", "")


def verify_api_key(request: Request) -> str:
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    if not hmac.compare_digest(key_hash, _API_KEY_HASH):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return key
