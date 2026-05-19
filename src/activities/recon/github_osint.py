import os
import asyncio
import json
from temporalio import activity


TRUFFLEHOG = os.getenv("TRUFFLEHOG_PATH", "trufflehog")


@activity.defn
async def run_github_osint(scope: list[str]) -> list[dict]:
    """
    Runs trufflehog against GitHub for any orgs/repos identified in scope.
    Only runs if scope contains github.com references.
    """
    github_targets = [s for s in scope if "github.com" in s.lower()]
    if not github_targets:
        activity.logger.info("No GitHub targets in scope, skipping OSINT")
        return []

    results: list[dict] = []
    for target in github_targets:
        activity.heartbeat(f"trufflehog: {target}")
        try:
            proc = await asyncio.create_subprocess_exec(
                TRUFFLEHOG, "github",
                "--repo", target,
                "--json",
                "--no-update",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            for line in stdout.decode().splitlines():
                if line.strip():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except (FileNotFoundError, asyncio.TimeoutError) as e:
            activity.logger.warning(f"trufflehog failed for {target}: {e}")

    return results
