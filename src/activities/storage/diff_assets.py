from temporalio import activity
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from src.db.session import engine
from src.db.models import Asset, ReconRun, AssetStatus
from src.workflows.types import DiffResult


@activity.defn
async def diff_assets(program_id: str, recon_run_id: str) -> dict:
    with Session(engine) as session:
        total = session.execute(
            select(func.count()).where(
                Asset.program_id == program_id,
                Asset.status == AssetStatus.active,
            )
        ).scalar_one()

        new_count = session.execute(
            select(func.count()).where(
                Asset.program_id == program_id,
                Asset.is_new == True,
            )
        ).scalar_one()

    return {"new_assets": new_count, "changed_assets": 0, "total_assets": total}
