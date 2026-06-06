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
        fail_recon_run,
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
        # out_of_scope is passed through every activity that touches assets so
        # filtering happens at enumeration time (fewer probes) AND at storage time
        # (validate_target enforces the boundary before any DB write).
        out_of_scope = program.get("out_of_scope", [])

        # Per-program constraints drive compliant recon (see Program Constraints
        # on the dashboard). These are plain data from an activity result, so
        # reading them here keeps the workflow deterministic.
        platform = program.get("platform", "")
        constraints = program.get("constraints") or {}
        # Stated cap is requests/minute; httpx wants requests/second. None lets
        # probe_hosts fall back to its global default.
        rpm = constraints.get("rate_limit_rpm")
        probe_rate_rps = max(1, rpm // 60) if rpm else None
        # Active tools (gowitness screenshots, katana JS crawl) send traffic to
        # the target, so they only run when the program explicitly permits active
        # scanning. Default is passive-only — safer and matches stricter programs.
        allow_active = bool(constraints.get("allow_active_scanning"))

        recon_run_id = await workflow.execute_activity(
            create_recon_run,
            args=[input.program_id, input.triggered_by],
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )

        # Everything after create_recon_run is wrapped so that any activity
        # failure marks the run as failed in the DB. Without this, a mid-workflow
        # crash leaves the record at status=running indefinitely.
        try:
            subdomains = await workflow.execute_activity(
                enumerate_subdomains,
                args=[scope, out_of_scope],
                start_to_close_timeout=_LONG,
                retry_policy=_RETRY,
            )

            probe_results = await workflow.execute_activity(
                probe_hosts,
                # rate + platform let probe_hosts honor the program's request cap
                # and attach any required identifying header (e.g. X-HackerOne-Research).
                args=[subdomains, probe_rate_rps, platform],
                start_to_close_timeout=_LONG,
                retry_policy=_RETRY,
            )

            live_urls = [r["url"] for r in probe_results if r.get("url")]

            import asyncio

            # Always-safe steps: fingerprint_tech works on probe_results (no
            # target traffic) and collect_hist_urls reads public archives (passive).
            tasks = [
                workflow.execute_activity(
                    fingerprint_tech,
                    probe_results,
                    start_to_close_timeout=_SHORT,
                    retry_policy=_RETRY,
                ),
                workflow.execute_activity(
                    collect_hist_urls,
                    scope,
                    start_to_close_timeout=_LONG,
                    retry_policy=_RETRY,
                ),
            ]
            # Active tools hit the target directly — only run with explicit opt-in.
            if allow_active:
                tasks.append(
                    workflow.execute_activity(
                        capture_screenshots,
                        live_urls,
                        start_to_close_timeout=_LONG,
                        retry_policy=_RETRY,
                    )
                )
                tasks.append(
                    workflow.execute_activity(
                        crawl_js_files,
                        live_urls,
                        start_to_close_timeout=_LONG,
                        retry_policy=_RETRY,
                    )
                )

            await asyncio.gather(*tasks)

            await workflow.execute_activity(
                run_github_osint,
                scope,
                start_to_close_timeout=_LONG,
                retry_policy=_RETRY,
            )

            asset_ids = await workflow.execute_activity(
                store_assets,
                # scope and out_of_scope must be passed explicitly so validate_target()
                # runs on every probe result before it is written to the database.
                # Without them the guard short-circuits (empty scope = skip validation)
                # and OOS assets would be stored.
                args=[input.program_id, recon_run_id, probe_results, scope, out_of_scope],
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

        except Exception:
            # Activity exhausted retries or raised a non-retryable error.
            # Mark the run failed so the health dashboard reflects reality,
            # then re-raise so Temporal still records the workflow as failed.
            await workflow.execute_activity(
                fail_recon_run,
                recon_run_id,
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )
            raise
