import json
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import Finding, FindingStatus


def _finding_dict(f: Finding) -> dict:
    return {
        "id": str(f.id),
        "program_id": str(f.program_id),
        "asset_id": str(f.asset_id) if f.asset_id else None,
        "title": f.title,
        "vuln_type": f.vuln_type,
        "severity": f.severity.value if f.severity else None,
        "status": f.status.value if f.status else None,
        "report_url": f.report_url,
        "payout_amount": float(f.payout_amount) if f.payout_amount else None,
        "submitted_at": f.submitted_at.isoformat() if f.submitted_at else None,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
        "paid_at": f.paid_at.isoformat() if f.paid_at else None,
    }


def list_findings_for_program(program_id: str) -> str:
    with Session(engine) as session:
        findings = session.execute(
            select(Finding)
            .where(Finding.program_id == program_id)
            .order_by(Finding.created_at.desc())
        ).scalars().all()
        return json.dumps([_finding_dict(f) for f in findings], indent=2)


def list_findings_by_status(status: str) -> str:
    with Session(engine) as session:
        try:
            status_enum = FindingStatus[status]
        except KeyError:
            return json.dumps({"error": f"Unknown status: {status}"})

        findings = session.execute(
            select(Finding)
            .where(Finding.status == status_enum)
            .order_by(Finding.created_at.desc())
        ).scalars().all()
        return json.dumps([_finding_dict(f) for f in findings], indent=2)
