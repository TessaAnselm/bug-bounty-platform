from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from src.workflows.types import ReconInput, ReconResult
    from src.activities.storage.store_assets import (
        load_program_scope,
        create_recon_run,
        store_assets,
        complete_recon_run,
    )
    from src.activities.storage.diff_assets import diff_assets
    from src.activities.recon.subdomain_enum import enumerate_subdomains
    from src.activities.recon.http_probe import probe_hosts
    from src.activities.recon.tech_fingerprint import fingerprint_tech
    from src.activities.recon.screenshot import capture_screenshots
    from src.activities.recon.js_crawl import crawl_js_files
    from src.activities.recon.hist_urls import collect_hist_urls
    from src.activities.recon.github_osint import run_github_osint
    from src.activities.notifications.discord_alert import send_discord_alert

_RETRY = RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=10))
_SHORT = timedelta(minutes=5)
_LONG = timedelta(minutes=30)


@workflow.defn
class ReconWorkflow:
    @workflow.run
    async def run(self, input: ReconInput) -> ReconResult:
        program = await workflow.execute_activity(
            load_program_scope,
            input.program_id,
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )
        scope = program["scope"]

        recon_run_id = await workflow.execute_activity(
            create_recon_run,
            args=[input.program_id, input.triggered_by],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        subdomains = await workflow.execute_activity(
            enumerate_subdomains,
            scope,
            start_to_close_timeout=_LONG,
            retry_policy=_RETRY,
        )

        probe_results = await workflow.execute_activity(
            probe_hosts,
            subdomains,
            start_to_close_timeout=_LONG,
            retry_policy=_RETRY,
        )

        live_urls = [r["url"] for r in probe_results if r.get("url")]

        tech_task = workflow.execute_activity(
            fingerprint_tech,
            probe_results,
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )
        screenshot_task = workflow.execute_activity(
            capture_screenshots,
            live_urls,
            start_to_close_timeout=_LONG,
            retry_policy=_RETRY,
        )
        js_task = workflow.execute_activity(
            crawl_js_files,
            live_urls,
            start_to_close_timeout=_LONG,
            retry_policy=_RETRY,
        )
        hist_task = workflow.execute_activity(
            collect_hist_urls,
            scope,
            start_to_close_timeout=_LONG,
            retry_policy=_RETRY,
        )

        import asyncio
        await asyncio.gather(tech_task, screenshot_task, js_task, hist_task)

        await workflow.execute_activity(
            run_github_osint,
            scope,
            start_to_close_timeout=_LONG,
            retry_policy=_RETRY,
        )

        asset_ids = await workflow.execute_activity(
            store_assets,
            args=[input.program_id, recon_run_id, probe_results],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        diff = await workflow.execute_activity(
            diff_assets,
            args=[input.program_id, recon_run_id],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        await workflow.execute_activity(
            complete_recon_run,
            args=[recon_run_id, diff["total_assets"], diff["new_assets"]],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        if diff["new_assets"] > 0:
            await workflow.execute_activity(
                send_discord_alert,
                f"🔍 Recon complete: **{diff['new_assets']} new assets** found (total: {diff['total_assets']})",
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )

        return ReconResult(
            recon_run_id=recon_run_id,
            assets_found=diff["total_assets"],
            new_assets=diff["new_assets"],
        )
