from temporalio import activity
from temporalio.exceptions import ApplicationError
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.db.session import engine
from src.db.models import Program, Asset, ReconRun, AssetType, AssetStatus, ReconStatus
from src.workflows.types import ProbeResult
from src.activities.storage.scope import validate_target
from src.activities.scoring.risk import calculate_risk_score, auto_tag


@activity.defn
async def load_program_scope(program_id: str) -> dict:
    with Session(engine) as session:
        program = session.get(Program, program_id)
        if not program:
            raise ApplicationError(f"Program {program_id} not found", non_retryable=True)
        if program.status.value != "active":
            raise ApplicationError(
                f"Program {program_id} is not active — complete ethics checklist first",
                non_retryable=True,
            )
        return {
            "name": program.name,
            "scope": program.scope or [],
            "out_of_scope": program.out_of_scope or [],
        }


@activity.defn
async def create_recon_run(program_id: str, triggered_by: str) -> str:
    with Session(engine) as session:
        run = ReconRun(
            program_id=program_id,
            triggered_by=triggered_by,
            status=ReconStatus.running,
            assets_found=0,
            new_assets=0,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return str(run.id)


@activity.defn
async def store_assets(
    program_id: str,
    recon_run_id: str,
    probe_results: list[dict],
    scope: list[str] | None = None,
    out_of_scope: list[str] | None = None,
) -> list[str]:
    asset_ids = []
    scope = scope or []
    out_of_scope = out_of_scope or []

    with Session(engine) as session:
        for r in probe_results:
            # Scope enforcement — drop out-of-scope assets before any DB write.
            # We always validate, even if scope is empty: an empty scope means
            # the program has no defined targets so nothing should be stored.
            # The original `if scope and ...` guard had a bug where an empty scope
            # list would skip validation entirely and store everything unchecked.
            if not validate_target(r["input"], scope, out_of_scope):
                continue
            existing = session.execute(
                select(Asset).where(
                    Asset.program_id == program_id,
                    Asset.type == AssetType.subdomain,
                    Asset.value == r["input"],
                )
            ).scalar_one_or_none()

            techs = r.get("technologies", [])
            http_status = r.get("status_code")
            risk = calculate_risk_score(r["input"], "subdomain", http_status, techs)
            tags = auto_tag(r["input"], "subdomain", techs)

            if existing:
                existing.technologies = techs
                existing.http_status = http_status
                existing.status = AssetStatus.active
                existing.is_new = False
                existing.risk_score = risk
                existing.tags = tags
                existing.source_tool = r.get("source_tool", "recon")
                session.flush()
                asset_ids.append(str(existing.id))
            else:
                asset = Asset(
                    program_id=program_id,
                    type=AssetType.subdomain,
                    value=r["input"],
                    status=AssetStatus.active,
                    technologies=techs,
                    ports=[r["port"]] if r.get("port") else [],
                    http_status=http_status,
                    is_new=True,
                    risk_score=risk,
                    tags=tags,
                    source_tool=r.get("source_tool", "recon"),
                    interesting=False,
                )
                session.add(asset)
                session.flush()
                asset_ids.append(str(asset.id))

        session.commit()

    return asset_ids


@activity.defn
async def complete_recon_run(recon_run_id: str, assets_found: int, new_assets: int) -> None:
    from datetime import datetime, timezone

    with Session(engine) as session:
        run = session.get(ReconRun, recon_run_id)
        if run:
            run.status = ReconStatus.completed
            run.assets_found = assets_found
            run.new_assets = new_assets
            run.completed_at = datetime.now(timezone.utc)
            session.commit()
