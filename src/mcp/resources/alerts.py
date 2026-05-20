import json
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from src.db.session import engine
from src.db.models import Alert


def get_unseen_alerts() -> str:
    with Session(engine) as session:
        unseen = session.execute(
            select(Alert)
            .where(Alert.seen == False)
            .order_by(Alert.created_at.desc())
        ).scalars().all()

        return json.dumps({
            "unseen_count": len(unseen),
            "alerts": [
                {
                    "id": str(a.id),
                    "program_id": str(a.program_id),
                    "asset_id": str(a.asset_id) if a.asset_id else None,
                    "type": a.type,
                    "message": a.message,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in unseen
            ],
        }, indent=2)
