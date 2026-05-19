import os
import asyncio
from temporalio import activity


GAU = os.getenv("GAU_PATH", "gau")


@activity.defn
async def collect_hist_urls(domains: list[str]) -> list[str]:
    if not domains:
        return []

    results: list[str] = []
    for domain in domains:
        activity.heartbeat(f"gau: {domain}")
        try:
            proc = await asyncio.create_subprocess_exec(
                GAU, domain,
                "--threads", "1",
                "--timeout", "30",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            results.extend(l.strip() for l in stdout.decode().splitlines() if l.strip())
        except (FileNotFoundError, asyncio.TimeoutError) as e:
            activity.logger.warning(f"gau failed for {domain}: {e}")

    return results
