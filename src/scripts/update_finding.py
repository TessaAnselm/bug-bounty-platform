"""
Usage:
  python src/scripts/update_finding.py --workflow-id <id> --status paid --payout 500
"""
import asyncio
import argparse
import os
from dotenv import load_dotenv
from temporalio.client import Client

load_dotenv()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Send status update signal to a FindingWorkflow")
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--status", required=True,
                        choices=["submitted", "triaged", "resolved", "duplicate", "not_applicable", "paid"])
    parser.add_argument("--payout", type=float, default=None)
    args = parser.parse_args()

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = os.getenv("TEMPORAL_PORT", "7233")
    client = await Client.connect(f"{host}:{port}")

    handle = client.get_workflow_handle(args.workflow_id)
    await handle.signal("update_status", args.status)
    print(f"Signal sent: status → {args.status}")

    if args.payout is not None:
        await handle.signal("set_payout", args.payout)
        print(f"Signal sent: payout → ${args.payout:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
