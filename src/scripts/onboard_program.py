"""
Usage:
  python src/scripts/onboard_program.py --name "Acme Corp" --platform hackerone \
    --scope "*.acme.com" "api.acme.com" --max-payout 10000
"""
import asyncio
import argparse
import os
from dotenv import load_dotenv
from temporalio.client import Client
from src.workflows.onboarding import ProgramOnboardingWorkflow
from src.workflows.types import OnboardingInput

load_dotenv()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Onboard a bug bounty program")
    parser.add_argument("--name", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--scope", nargs="+", required=True)
    parser.add_argument("--out-of-scope", nargs="*", default=[])
    parser.add_argument("--max-payout", type=int, default=None)
    args = parser.parse_args()

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = os.getenv("TEMPORAL_PORT", "7233")
    client = await Client.connect(f"{host}:{port}")

    input = OnboardingInput(
        name=args.name,
        platform=args.platform,
        scope=args.scope,
        out_of_scope=args.out_of_scope,
        max_payout=args.max_payout,
    )

    handle = await client.start_workflow(
        ProgramOnboardingWorkflow.run,
        input,
        id=f"onboarding-{args.name.lower().replace(' ', '-')}",
        task_queue="bounty-task-queue",
    )

    print(f"Onboarding started — workflow ID: {handle.id}")
    result = await handle.result()
    print(f"Program ID:   {result.program_id}")
    print(f"Recon ID:     {result.recon_workflow_id}")
    print(f"Monitor ID:   {result.monitor_workflow_id}")


if __name__ == "__main__":
    asyncio.run(main())
