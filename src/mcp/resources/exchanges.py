import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import HttpExchange
from src.lib.compliance import redact_headers, redact_text


def _exchange_dict(ex: HttpExchange) -> dict:
    """Exchange for AI review. Request headers are redacted (they may carry the
    hunter's own session cookies/tokens); response body is excerpted."""
    return {
        "id": str(ex.id),
        "method": ex.request_method,
        "url": ex.request_url,
        "request_headers": redact_headers(ex.request_headers),
        "request_body": redact_text(ex.request_body),
        "response_status": ex.response_status,
        "response_time_ms": ex.response_time_ms,
        "response_excerpt": redact_text((ex.response_body or "")[:4000]),
        "label": ex.label,
        "note": ex.note,
        "created_at": ex.created_at.isoformat() if ex.created_at else None,
    }


def list_exchanges_for_session(session_id: str) -> str:
    with Session(engine) as session:
        rows = session.execute(
            select(HttpExchange)
            .where(HttpExchange.hunt_session_id == session_id)
            .order_by(HttpExchange.created_at.desc())
            .limit(50)
        ).scalars().all()
        return json.dumps([_exchange_dict(e) for e in rows], indent=2)
