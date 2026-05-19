import os
import asyncio
from pathlib import Path
from temporalio import activity


GOWITNESS = os.getenv("GOWITNESS_PATH", "gowitness")
SCREENSHOT_DIR = Path("artifacts/screenshots")


@activity.defn
async def capture_screenshots(urls: list[str]) -> list[dict]:
    if not urls:
        return []

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    activity.heartbeat(f"screenshots: {len(urls)} urls")

    results = []
    try:
        proc = await asyncio.create_subprocess_exec(
            GOWITNESS, "file", "-f", "/dev/stdin",
            "--screenshot-path", str(SCREENSHOT_DIR),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        input_data = "\n".join(urls).encode()
        await asyncio.wait_for(proc.communicate(input_data), timeout=300)

        for url in urls:
            safe_name = url.replace("://", "_").replace("/", "_").replace(":", "_")
            path = SCREENSHOT_DIR / f"{safe_name}.png"
            if path.exists():
                results.append({"url": url, "path": str(path)})
    except (FileNotFoundError, asyncio.TimeoutError) as e:
        activity.logger.warning(f"gowitness failed: {e}")

    return results
