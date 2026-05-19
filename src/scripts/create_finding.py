"""
Usage:
  python src/scripts/create_finding.py \
    --program-id <uuid> \
    --title "IDOR on /api/v1/users" \
    --vuln-type IDOR \
    --severity high
"""
import asyncio
import argparse
import os
from dotenv import load_dotenv
from temporalio.client import Client
from src.workflows.finding import FindingWorkflow
from src.workflows.types import FindingInput

load_dotenv()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create and track a finding")
    parser.add_argument("--program-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--vuln-type", required=True)
    parser.add_argument("--severity", required=True,
                        choices=["critical", "high", "medium", "low", "informational"])
    parser.add_argument("--asset-id", default=None)
    args = parser.parse_args()

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = os.getenv("TEMPORAL_PORT", "7233")
    client = await Client.connect(f"{host}:{port}")

    input = FindingInput(
        program_id=args.program_id,
        title=args.title,
        vuln_type=args.vuln_type,
        severity=args.severity,
        asset_id=args.asset_id,
    )

    handle = await client.start_workflow(
        FindingWorkflow.run,
        input,
        id=f"finding-{args.program_id}-{args.title[:20].replace(' ', '-').lower()}",
        task_queue="bounty-task-queue",
    )

    print(f"Finding workflow started — ID: {handle.id}")
    print("Waiting for terminal status signal (submitted/resolved/paid/duplicate)...")
    print(f"Send signal: python src/scripts/update_finding.py --workflow-id {handle.id} --status submitted")


if __name__ == "__main__":
    asyncio.run(main())
