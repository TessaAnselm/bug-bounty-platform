"""
Single source of truth for what a recon run will actually do, derived from a
program's constraints. The ReconWorkflow uses this to decide behavior AND the
program page renders it — so "what the platform shows" and "what Run recon does"
can never drift apart.

Each tool is described by:
  gated_by_active — only runs when the program allows active scanning
  target_facing   — sends requests to the program's own assets (subject to the
                    rate limit + required headers). Passive tools query
                    third-party data (crt.sh, web archives, GitHub) and never
                    touch the target.
"""

DEFAULT_RPS = 3  # must match RATE_LIMIT fallback in activities/recon/http_probe.py

# (name, gated_by_active, target_facing) — mirrors the activities in ReconWorkflow.
_TOOLS = [
    ("subfinder", False, False),   # subdomain enumeration (passive sources)
    ("httpx",     False, True),    # HTTP probe — the always-on target-facing step
    ("fingerprint", False, False), # tech detect on probe results (no new traffic)
    ("gau",       False, False),   # historical URLs from web archives (passive)
    ("github",    False, False),   # GitHub code/OSINT via GitHub API (passive)
    ("katana",    True,  True),    # JS/endpoint crawl — active
    ("gowitness", True,  True),    # screenshots — active
]


def effective_rps(constraints: dict | None) -> int:
    """The requests/second the probe will use for target-facing tools.

    Mirrors ReconWorkflow: program rate_limit_rpm (÷60, floored to >=1) when set,
    otherwise the global default.
    """
    rpm = (constraints or {}).get("rate_limit_rpm")
    if rpm and rpm > 0:
        return max(1, int(rpm) // 60)
    return DEFAULT_RPS


def recon_plan(constraints: dict | None) -> dict:
    """Return exactly what Run recon will execute for these constraints."""
    active = bool((constraints or {}).get("allow_active_scanning"))
    rpm = (constraints or {}).get("rate_limit_rpm")
    rps = effective_rps(constraints)

    will_run = [(n, tf) for (n, gated, tf) in _TOOLS if not gated or active]
    skipped = [n for (n, gated, tf) in _TOOLS if gated and not active]

    return {
        "active_scanning": active,
        "rate_rps": rps,
        "rate_source": f"program cap ({rpm}/min)" if rpm else f"default ({DEFAULT_RPS}/sec)",
        "tools_running": [n for (n, tf) in will_run],
        "target_facing": [n for (n, tf) in will_run if tf],   # subject to rate + headers
        "passive": [n for (n, tf) in will_run if not tf],     # no target traffic
        "tools_skipped": skipped,                             # active tools, off by default
    }
