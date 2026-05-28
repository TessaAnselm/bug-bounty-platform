import os
import asyncio
from temporalio import activity


KATANA = os.getenv("KATANA_PATH", "katana")
RATE_LIMIT = int(os.getenv("RECON_RATE_LIMIT_RPS", "5"))


@activity.defn
async def crawl_js_files(urls: list[str]) -> list[str]:
    if not urls:
        return []

    activity.heartbeat(f"katana: crawling {len(urls)} urls")

    try:
        proc = await asyncio.create_subprocess_exec(
            KATANA,
            "-list", "/dev/stdin",
            "-silent",
            "-js-crawl",
            "-rate-limit", str(RATE_LIMIT),
            "-timeout", "15",
            "-depth", "2",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        input_data = "\n".join(urls).encode()
        stdout, _ = await asyncio.wait_for(proc.communicate(input_data), timeout=300)
        lines = [l.strip() for l in stdout.decode().splitlines() if l.strip()]
        return lines[:2000]  # cap to stay within Temporal's 2MB payload limit
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        activity.logger.warning(f"katana failed: {e}")
        return []
