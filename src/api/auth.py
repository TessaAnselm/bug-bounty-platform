import os
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("DASHBOARD_API_KEY", "changeme")


def verify_api_key(request: Request) -> str:
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not key or key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return key
