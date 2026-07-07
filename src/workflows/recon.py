import os
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
    from src.activities.recon.screenshot import capture_screenshots
    from src.activities.recon.js_crawl import crawl_js_files
    from src.activities.recon.hist_urls import collect_hist_urls
    from src.activities.recon.github_osint import run_github_osint
    from src.activities.notifications.discord_alert import send_discord_alert
    from src.lib.recon_plan import effective_rps

_RETRY = RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=10))
_SHORT = timedelta(minutes=5)
_LONG = timedelta(minutes=30)
# Hosts are probed + stored in batches of this size so no single probe activity
# exceeds its timeout and no Temporal payload gets large — this is what lets recon
# scale to big wildcard scopes (e.g. Kong's *.konghq.com, 18K+ subdomains).
_BATCH_SIZE = int(os.getenv("RECON_BATCH_SIZE", "500"))


def batches(seq: list, size: int) -> list[list]:
    """Split a list into consecutive chunks of at most `size` (deterministic —
    safe to call inside the workflow)."""
    size = max(1, size)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


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
        # effective_rps() is the SAME function the program page uses to display the
        # rate, so what the UI shows == what the probe actually uses. Active tools
        # (katana/gowitness) send traffic to the target, so they only run when the
        # program explicitly permits active scanning (default: passive-only).
        probe_rate_rps = effective_rps(constraints)
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

            import asyncio

            # Probe + store in batches: chunk the host list, probe one batch,
            # store its results to the DB immediately, then move to the next.
            # This keeps every probe under its timeout and every Temporal payload
            # small (no giant result list crosses the boundary), so recon scales
            # to large wildcard scopes. Assets appear incrementally, and a
            # mid-run failure keeps everything already stored.
            # tech-detect now runs *inside* the probe (httpx -tech-detect), so
            # there is no separate fingerprint pass to also scale.
            live_urls: list[str] = []
            for batch in batches(subdomains, _BATCH_SIZE):
                batch_results = await workflow.execute_activity(
                    probe_hosts,
                    # rate + platform: honor the program's request cap and attach
                    # any required identifying header (e.g. X-HackerOne-Research).
                    args=[batch, probe_rate_rps, platform],
                    start_to_close_timeout=_LONG,
                    retry_policy=_RETRY,
                )
                # scope + out_of_scope passed explicitly so validate_target() runs
                # on every result before any DB write (empty scope = reject all).
                await workflow.execute_activity(
                    store_assets,
                    args=[input.program_id, recon_run_id, batch_results, scope, out_of_scope],
                    start_to_close_timeout=_SHORT,
                    retry_policy=_RETRY,
                )
                live_urls.extend(r["url"] for r in batch_results if r.get("url"))

            # Passive post-processing runs once (operates on scope roots), plus
            # active tools on the accumulated live URLs when explicitly permitted.
            tasks = [
                workflow.execute_activity(
                    collect_hist_urls,
                    scope,
                    start_to_close_timeout=_LONG,
                    retry_policy=_RETRY,
                ),
            ]
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
