import os
import asyncio
import re
from temporalio import activity


SUBFINDER = os.getenv("SUBFINDER_PATH", "subfinder")
_SAFE_DOMAIN = re.compile(r"^[a-zA-Z0-9.\-*]+$")


def _extract_root_domains(scope: list[str]) -> list[str]:
    """Pull enumerable root domains from scope entries."""
    domains = []
    for entry in scope:
        entry = entry.strip().lstrip("*.")
        parts = entry.split("/")[0]  # strip any URL paths
        if parts and _SAFE_DOMAIN.match(parts):
            domains.append(parts)
    return list(set(domains))


@activity.defn
async def enumerate_subdomains(scope: list[str]) -> list[str]:
    domains = _extract_root_domains(scope)
    if not domains:
        return []

    results: list[str] = []
    for domain in domains:
        activity.heartbeat(f"subfinder: {domain}")
        try:
            proc = await asyncio.create_subprocess_exec(
                SUBFINDER, "-d", domain, "-silent",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            lines = [l.strip() for l in stdout.decode().splitlines() if l.strip()]
            results.extend(lines)
        except (FileNotFoundError, asyncio.TimeoutError) as e:
            activity.logger.warning(f"subfinder failed for {domain}: {e}")

    # always include scope domains themselves
    for d in domains:
        if d not in results:
            results.append(d)

    return list(set(results))
