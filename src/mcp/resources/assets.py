import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import Asset


def _asset_dict(a: Asset) -> dict:
    return {
        "id": str(a.id),
        "program_id": str(a.program_id),
        "type": a.type.value if a.type else None,
        "value": a.value,
        "status": a.status.value if a.status else None,
        "technologies": a.technologies,
        "ports": a.ports,
        "http_status": a.http_status,
        "is_new": a.is_new,
        "first_seen": a.first_seen.isoformat() if a.first_seen else None,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
    }


def list_assets_for_program(program_id: str) -> str:
    with Session(engine) as session:
        assets = session.execute(
            select(Asset)
            .where(Asset.program_id == program_id)
            .order_by(Asset.is_new.desc(), Asset.first_seen.desc())
        ).scalars().all()
        return json.dumps([_asset_dict(a) for a in assets], indent=2)


def list_new_assets(program_id: str) -> str:
    with Session(engine) as session:
        assets = session.execute(
            select(Asset)
            .where(Asset.program_id == program_id, Asset.is_new == True)
            .order_by(Asset.first_seen.desc())
        ).scalars().all()
        return json.dumps([_asset_dict(a) for a in assets], indent=2)
