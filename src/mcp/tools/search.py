import json
from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from src.db.session import engine
from src.db.models import Asset, Program, Finding, AssetType, AssetStatus


def search_assets(query: str, program_id: str | None = None) -> str:
    q = query.strip().lower()
    if not q:
        return json.dumps({"error": "query must not be empty"})

    with Session(engine) as session:
        stmt = select(Asset).where(Asset.value.ilike(f"%{q}%"))
        if program_id:
            stmt = stmt.where(Asset.program_id == program_id)
        stmt = stmt.order_by(Asset.last_seen.desc()).limit(50)

        assets = session.execute(stmt).scalars().all()
        results = [
            {
                "id": str(a.id),
                "program_id": str(a.program_id),
                "type": a.type.value if a.type else None,
                "value": a.value,
                "status": a.status.value if a.status else None,
                "http_status": a.http_status,
                "technologies": a.technologies,
                "is_new": a.is_new,
                "first_seen": a.first_seen.isoformat() if a.first_seen else None,
                "last_seen": a.last_seen.isoformat() if a.last_seen else None,
            }
            for a in assets
        ]
        return json.dumps({"count": len(results), "assets": results}, indent=2)


def summarize_program(program_id: str) -> str:
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            return json.dumps({"error": f"Program {program_id} not found"})

        all_assets = session.execute(
            select(Asset).where(Asset.program_id == program_id)
        ).scalars().all()

        all_findings = session.execute(
            select(Finding).where(Finding.program_id == program_id)
        ).scalars().all()

        asset_by_type: dict[str, int] = {}
        for a in all_assets:
            t = a.type.value if a.type else "unknown"
            asset_by_type[t] = asset_by_type.get(t, 0) + 1

        finding_by_severity: dict[str, int] = {}
        finding_by_status: dict[str, int] = {}
        total_payout = 0.0
        for f in all_findings:
            sev = f.severity.value if f.severity else "unknown"
            sta = f.status.value if f.status else "unknown"
            finding_by_severity[sev] = finding_by_severity.get(sev, 0) + 1
            finding_by_status[sta] = finding_by_status.get(sta, 0) + 1
            if f.payout_amount:
                total_payout += float(f.payout_amount)

        new_assets = sum(1 for a in all_assets if a.is_new)

        return json.dumps({
            "program_id": program_id,
            "program_name": program.name,
            "platform": program.platform,
            "status": program.status.value if program.status else None,
            "max_payout": float(program.max_payout) if program.max_payout else None,
            "assets": {
                "total": len(all_assets),
                "new": new_assets,
                "by_type": asset_by_type,
            },
            "findings": {
                "total": len(all_findings),
                "total_payout": total_payout,
                "by_severity": finding_by_severity,
                "by_status": finding_by_status,
            },
        }, indent=2)
