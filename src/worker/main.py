import asyncio
import os
from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from src.workflows.onboarding import ProgramOnboardingWorkflow
from src.workflows.recon import ReconWorkflow
from src.workflows.finding import FindingWorkflow
from src.workflows.monitor import MonitorWorkflow

from src.activities.storage.store_assets import (
    load_program_scope,
    create_recon_run,
    store_assets,
    complete_recon_run,
    fail_recon_run,
)
from src.activities.storage.diff_assets import diff_assets
from src.activities.storage.programs import (
    store_program,
    create_finding,
    update_finding_status,
    record_outcome,
)
from src.activities.scoring.score_program import score_program
from src.activities.notifications.discord_alert import send_discord_alert
from src.activities.recon.subdomain_enum import enumerate_subdomains
from src.activities.recon.http_probe import probe_hosts
from src.activities.recon.tech_fingerprint import fingerprint_tech
from src.activities.recon.screenshot import capture_screenshots
from src.activities.recon.js_crawl import crawl_js_files
from src.activities.recon.hist_urls import collect_hist_urls
from src.activities.recon.github_osint import run_github_osint

load_dotenv()

TASK_QUEUE = "bounty-task-queue"
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost")
TEMPORAL_PORT = os.getenv("TEMPORAL_PORT", "7233")


async def main() -> None:
    client = await Client.connect(f"{TEMPORAL_HOST}:{TEMPORAL_PORT}")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            ProgramOnboardingWorkflow,
            ReconWorkflow,
            FindingWorkflow,
            MonitorWorkflow,
        ],
        activities=[
            load_program_scope,
            create_recon_run,
            store_assets,
            complete_recon_run,
            fail_recon_run,
            diff_assets,
            store_program,
            create_finding,
            update_finding_status,
            record_outcome,
            score_program,
            send_discord_alert,
            enumerate_subdomains,
            probe_hosts,
            fingerprint_tech,
            capture_screenshots,
            crawl_js_files,
            collect_hist_urls,
            run_github_osint,
        ],
    )

    print(f"Worker started — task queue: {TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
