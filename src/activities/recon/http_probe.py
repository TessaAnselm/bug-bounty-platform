import os
import asyncio
import json
from temporalio import activity


HTTPX = os.getenv("HTTPX_PATH", "httpx")
# Conservative global default (requests/second). Most mature/managed programs
# expect gentle traffic, so we default low and stay compliant-by-default; a
# program's per-program rate_limit constraint can raise this when explicitly
# permitted. See ReconWorkflow → probe_hosts(rate_limit_rps=...).
RATE_LIMIT = int(os.getenv("RECON_RATE_LIMIT_RPS", "3"))
MAX_THREADS = int(os.getenv("RECON_MAX_CONCURRENT", "50"))
# HackerOne programs require this identifying header on every request. Set your
# H1 username here; the probe attaches "X-HackerOne-Research: <username>" for
# hackerone-platform programs so recon traffic is compliant and attributable.
HACKERONE_RESEARCH_USERNAME = os.getenv("HACKERONE_RESEARCH_USERNAME", "").strip()


@activity.defn
async def probe_hosts(
    hosts: list[str],
    rate_limit_rps: int | None = None,
    platform: str = "",
) -> list[dict]:
    if not hosts:
        return []

    activity.heartbeat(f"probing {len(hosts)} hosts")

    # Per-program rate limit (from constraints) overrides the global default so
    # we never exceed a program's stated request cap (e.g. 3 req/s for 23andMe).
    rate = rate_limit_rps if rate_limit_rps and rate_limit_rps > 0 else RATE_LIMIT

    cmd = [
        HTTPX,
        "-l", "/dev/stdin",
        "-json",
        "-silent",
        # No -tech-detect here — fingerprint_tech runs as a separate parallel
        # activity later in ReconWorkflow and does the same job. Including it
        # here made httpx 10x slower and caused consistent 600s timeouts.
        "-rate-limit", str(rate),
        "-threads", str(MAX_THREADS),
        "-timeout", "5",
    ]
    # Compliance header — required by HackerOne program rules. Without a
    # configured username we omit it (and you should not probe programs that
    # mandate it until it's set).
    if platform == "hackerone" and HACKERONE_RESEARCH_USERNAME:
        cmd += ["-H", f"X-HackerOne-Research: {HACKERONE_RESEARCH_USERNAME}"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        input_data = "\n".join(hosts).encode()
        # Heartbeat every 30s so Temporal doesn't consider the activity dead.
        async def _heartbeat_loop() -> None:
            i = 0
            while True:
                await asyncio.sleep(30)
                i += 1
                activity.heartbeat(f"httpx still running ({i * 30}s)")

        heartbeat_task = asyncio.create_task(_heartbeat_loop())
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(input_data), timeout=300)
        except asyncio.TimeoutError:
            # Kill the subprocess so it doesn't keep running after we give up.
            proc.kill()
            await proc.wait()
            raise
        finally:
            heartbeat_task.cancel()
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        activity.logger.warning(f"httpx failed: {type(e).__name__}: {e}")
        return []

    results = []
    for line in stdout.decode().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            results.append({
                "url": data.get("url", ""),
                "input": data.get("input", ""),
                "status_code": data.get("status_code", 0),
                "content_length": data.get("content_length", 0),
                "technologies": data.get("tech", []),
                "webserver": data.get("webserver", ""),
                "title": data.get("title", ""),
                "host": data.get("host", ""),
                "port": str(data.get("port", "")),
                "scheme": data.get("scheme", "https"),
            })
        except json.JSONDecodeError:
            continue

    return results
