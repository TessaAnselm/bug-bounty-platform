from temporalio import activity
from temporalio.exceptions import ApplicationError
from sqlalchemy.orm import Session
from src.db.session import engine
from src.db.models import Program, Finding, Outcome, ProgramStatus, Severity, FindingStatus


@activity.defn
async def store_program(
    name: str,
    platform: str,
    scope: list[str],
    out_of_scope: list[str],
    max_payout: int | None,
) -> str:
    with Session(engine) as session:
        program = Program(
            name=name,
            platform=platform,
            scope=scope,
            out_of_scope=out_of_scope,
            max_payout=max_payout,
            # Onboards as draft — recon is gated until the compliance checklist
            # is completed and the program is explicitly activated.
            status=ProgramStatus.draft,
        )
        session.add(program)
        session.commit()
        session.refresh(program)
        return str(program.id)


@activity.defn
async def create_finding(
    program_id: str,
    title: str,
    vuln_type: str,
    severity: str,
    asset_id: str | None = None,
) -> str:
    with Session(engine) as session:
        finding = Finding(
            program_id=program_id,
            asset_id=asset_id,
            title=title,
            vuln_type=vuln_type,
            severity=Severity[severity],
            status=FindingStatus.draft,
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        return str(finding.id)


@activity.defn
async def update_finding_status(finding_id: str, new_status: str) -> None:
    from datetime import datetime, timezone

    with Session(engine) as session:
        finding = session.get(Finding, finding_id)
        if not finding:
            raise ApplicationError(f"Finding {finding_id} not found", non_retryable=True)
        finding.status = FindingStatus[new_status]
        now = datetime.now(timezone.utc)
        if new_status == "submitted":
            finding.submitted_at = now
        elif new_status == "triaged":
            finding.triaged_at = now
        elif new_status in ("resolved", "duplicate", "not_applicable", "paid"):
            finding.resolved_at = now
        if new_status == "paid":
            finding.paid_at = now
        session.commit()


@activity.defn
async def record_outcome(
    finding_id: str,
    result: str,
    payout_amount: float | None,
    time_spent_hours: float | None,
    lessons: str | None,
) -> None:
    with Session(engine) as session:
        outcome = Outcome(
            finding_id=finding_id,
            result=result,
            payout_amount=payout_amount,
            time_spent_hours=time_spent_hours,
            lessons=lessons,
        )
        session.add(outcome)
        session.commit()
