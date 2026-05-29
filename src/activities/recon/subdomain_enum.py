import os
import asyncio
import re
from temporalio import activity
from src.activities.storage.scope import validate_target


# Resolved from env so the binary path can be overridden in CI or on a VM
# without changing code. Defaults to "subfinder" on the system PATH.
SUBFINDER = os.getenv("SUBFINDER_PATH", "subfinder")

# Allowlist for domain characters — rejects anything with spaces, shell
# metacharacters, or other injection attempts before passing to subprocess.
_SAFE_DOMAIN = re.compile(r"^[a-zA-Z0-9.\-*]+$")


def _extract_root_domains(scope: list[str], out_of_scope: list[str]) -> list[str]:
    """Return root domains that subfinder should enumerate, excluding OOS roots.

    Why we strip to root domains: subfinder takes a root domain (e.g. konghq.com)
    and discovers all subdomains beneath it. Wildcards like *.api.konghq.com and
    full URLs like https://cloud.konghq.com both reduce to their root domain.

    Why we exclude OOS roots: some programs have a root domain in OOS even though
    a specific subdomain is in scope (e.g. insomnia.rest is OOS but
    app.insomnia.rest is in scope). We skip enumerating the OOS root entirely —
    validate_target() in store_assets enforces the per-asset boundary when results
    are saved, so only the explicitly in-scope subdomain would be stored anyway.
    Running subfinder on an OOS root wastes time and probes hosts we can't report on.

    Non-domain scope items (e.g. "Kong Mesh", "Insomnia CLI") fail the regex and
    are silently skipped — they are executable products, not enumerable domains.
    """
    oos_roots: set[str] = set()
    for entry in out_of_scope:
        root = entry.strip().lstrip("*.").split("/")[0].lower()
        if root and _SAFE_DOMAIN.match(root):
            oos_roots.add(root)

    domains: list[str] = []
    for entry in scope:
        root = entry.strip().lstrip("*.").split("/")[0].lower()
        if root and _SAFE_DOMAIN.match(root) and root not in oos_roots:
            domains.append(root)

    return list(set(domains))


@activity.defn
async def enumerate_subdomains(scope: list[str], out_of_scope: list[str] | None = None) -> list[str]:
    """Run subfinder against every in-scope root domain and return discovered subdomains.

    out_of_scope is optional for backwards compatibility — callers that haven't
    been updated to pass it yet will get the old behaviour (no OOS filtering at
    enumeration time, relying solely on validate_target at store time).

    Why we include the root domains themselves: subfinder only returns discovered
    children, not the apex. If cloud.konghq.com is in scope, we want to probe it
    directly even if subfinder finds nothing beneath it.

    Heartbeat is sent per-domain so Temporal knows the activity is still alive
    during a long subfinder run and doesn't time it out prematurely.
    """
    oos = out_of_scope or []
    domains = _extract_root_domains(scope, oos)
    if not domains:
        return []

    results: list[str] = []
    for domain in domains:
        # Temporal heartbeat — required for long-running activities so the server
        # doesn't assume the worker crashed and schedule a retry mid-run.
        activity.heartbeat(f"subfinder: {domain}")
        try:
            proc = await asyncio.create_subprocess_exec(
                SUBFINDER, "-d", domain, "-silent",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            lines = [line.strip() for line in stdout.decode().splitlines() if line.strip()]
            results.extend(lines)
        except FileNotFoundError:
            activity.logger.warning(f"subfinder not found — install it with: brew install subfinder")
        except asyncio.TimeoutError:
            activity.logger.warning(f"subfinder timed out for {domain} after 300s")

    # Always include the root domains themselves — subfinder only returns children.
    for d in domains:
        if d not in results:
            results.append(d)

    all_found = list(set(results))

    # Filter to only subdomains that pass scope validation before returning.
    # konghq.com has 18K+ subdomains — probing all of them takes 30+ minutes
    # and validate_target() in store_assets rejects 99% anyway (scope only covers
    # specific wildcards like *.api.konghq.com, not all of konghq.com).
    # Filtering here means httpx only probes hosts we can actually report on.
    if scope:
        in_scope = [h for h in all_found if validate_target(h, scope, oos)]
        activity.logger.info(f"scope filter: {len(all_found)} found → {len(in_scope)} in scope")
        return in_scope

    return all_found
