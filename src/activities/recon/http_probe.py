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
            "-tech-detect",
            "-rate-limit", str(RATE_LIMIT),
            "-threads", str(MAX_THREADS),
            "-timeout", "10",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        input_data = "\n".join(hosts).encode()
        stdout, _ = await asyncio.wait_for(proc.communicate(input_data), timeout=300)
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        activity.logger.warning(f"httpx failed: {e}")
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
