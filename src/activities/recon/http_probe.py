import os
import asyncio
import json
from temporalio import activity


HTTPX = os.getenv("HTTPX_PATH", "httpx")
RATE_LIMIT = int(os.getenv("RECON_RATE_LIMIT_RPS", "5"))
MAX_THREADS = int(os.getenv("RECON_MAX_CONCURRENT", "2"))


@activity.defn
async def probe_hosts(hosts: list[str]) -> list[dict]:
    if not hosts:
        return []

    activity.heartbeat(f"probing {len(hosts)} hosts")

    try:
        proc = await asyncio.create_subprocess_exec(
            HTTPX,
            "-l", "/dev/stdin",
            "-json",
            "-silent",
            # No -tech-detect here — fingerprint_tech runs as a separate parallel
            # activity later in ReconWorkflow and does the same job. Including it
            # here made httpx 10x slower and caused consistent 600s timeouts.
            "-rate-limit", str(RATE_LIMIT),
            "-threads", str(MAX_THREADS),
            "-timeout", "10",
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
