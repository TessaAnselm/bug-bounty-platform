#!/usr/bin/env python3
"""
Program selection tool — fetches live data from bounty-targets-data and
scores programs using the platform's 5-dimension model. Outputs a ranked list.

Usage:
    python scripts/select_program.py                  # score all platforms
    python scripts/select_program.py --platform h1    # HackerOne only
    python scripts/select_program.py --platform bc    # Bugcrowd only
    python scripts/select_program.py --top 20         # show top 20 (default 15)
    python scripts/select_program.py --detail 'Name'  # score breakdown
"""

import argparse
import sys
import httpx

SOURCES = {
    "h1": {
        "name": "HackerOne",
        "url": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/hackerone_data.json",
    },
    "bc": {
        "name": "Bugcrowd",
        "url": "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/bugcrowd_data.json",
    },
}


# ── Scoring ───────────────────────────────────────────────────────────────

def _payout_score(program: dict) -> float:
    """
    bounty-targets-data doesn't include max payout amounts.
    Approximate from response time and managed status.
    """
    score = 40.0
    if program.get("managed_program"):
        score += 20.0
    avg_bounty_time = program.get("average_time_to_bounty_awarded")
    if avg_bounty_time:
        if avg_bounty_time < 30:
            score += 25.0
        elif avg_bounty_time < 90:
            score += 15.0
        elif avg_bounty_time < 180:
            score += 5.0
    return min(100.0, score)


def _scope_score(scope_items: list[str]) -> float:
    if not scope_items:
        return 0.0
    score = min(50.0, len(scope_items) * 4.0)
    joined = " ".join(scope_items).lower()
    if "*" in joined:
        score += 30.0
    types = set()
    for s in scope_items:
        sl = s.lower()
        if "." in s:
            types.add("domain")
        if "api" in sl:
            types.add("api")
        if sl.startswith("http"):
            types.add("url")
    score += len(types) * 5.0
    return min(100.0, score)


def _competition_score(program: dict, scope_count: int) -> float:
    """
    Lower scope + slower response time + non-managed = less competition.
    """
    score = 70.0
    # large scope = more hunters = more competition
    if scope_count > 50:
        score -= 30.0
    elif scope_count > 20:
        score -= 15.0
    elif scope_count <= 5:
        score += 10.0
    # fast response = popular = competitive
    avg_response = program.get("average_time_to_first_program_response")
    if avg_response:
        if avg_response < 3:
            score -= 10.0   # very fast = very popular
        elif avg_response > 14:
            score += 10.0   # slow = less saturated
    return min(100.0, max(0.0, score))


def _fit_score(scope_items: list[str], name: str) -> float:
    combined = " ".join(scope_items).lower() + " " + name.lower()
    score = 50.0

    if any(kw in combined for kw in ["ai", "ml", "llm", "model", "claude", "gpt", "openai", "anthropic"]):
        score += 35.0
    if any(kw in combined for kw in ["api", "rest", "graphql", "grpc"]):
        score += 30.0
    if any(kw in combined for kw in ["oauth", "sso", "auth", "saml", "login"]):
        score += 25.0
    if any(kw in combined for kw in ["aws", "gcp", "azure", "cloud", "s3"]):
        score += 15.0
    if any(kw in combined for kw in ["mobile", "ios", "android"]):
        score += 10.0
    if any(kw in combined for kw in ["ai", "ml", "llm", "anthropic", "openai"]):
        score *= 1.3

    return min(100.0, score)


def _momentum_score(program: dict) -> float:
    score = 50.0
    efficiency = program.get("response_efficiency_percentage")
    if efficiency:
        if efficiency >= 95:
            score += 20.0
        elif efficiency >= 80:
            score += 10.0
        elif efficiency < 60:
            score -= 20.0
    return min(100.0, max(0.0, score))


def _signals(scope_items: list[str], name: str) -> list[str]:
    combined = " ".join(scope_items).lower() + " " + name.lower()
    sigs = []
    if any(kw in combined for kw in ["ai", "ml", "llm", "anthropic", "openai"]):
        sigs.append("AI/LLM")
    if any(kw in combined for kw in ["api", "graphql", "grpc"]):
        sigs.append("API")
    if any(kw in combined for kw in ["oauth", "sso", "auth"]):
        sigs.append("Auth")
    if "*" in " ".join(scope_items):
        sigs.append("Wildcard")
    if any(kw in combined for kw in ["aws", "gcp", "azure", "cloud"]):
        sigs.append("Cloud")
    return sigs


def score_program(program: dict) -> dict:
    scope_items = program.get("_scope_items", [])
    name = program.get("name", "")

    payout   = _payout_score(program)
    scope    = _scope_score(scope_items)
    comp     = _competition_score(program, len(scope_items))
    fit      = _fit_score(scope_items, name)
    momentum = _momentum_score(program)

    total = (
        payout   * 0.20
        + scope  * 0.20
        + comp   * 0.25
        + fit    * 0.25
        + momentum * 0.10
    )

    return {
        "name": name,
        "platform": program.get("_platform", ""),
        "url": program.get("url", ""),
        "managed": program.get("managed_program", False),
        "response_days": program.get("average_time_to_first_program_response"),
        "efficiency": program.get("response_efficiency_percentage"),
        "scope_count": len(scope_items),
        "total_score": round(total, 1),
        "payout_score": round(payout, 1),
        "scope_score": round(scope, 1),
        "competition_score": round(comp, 1),
        "fit_score": round(fit, 1),
        "momentum_score": round(momentum, 1),
        "signals": _signals(scope_items, name),
    }


# ── Fetch and parse ───────────────────────────────────────────────────────

def fetch(url: str) -> list[dict]:
    print(f"  Fetching {url.split('/')[-1]} ...", end=" ", flush=True)
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
        print("OK")
        return r.json()
    except Exception as e:
        print(f"FAILED ({e})")
        return []


def parse_h1(programs: list[dict]) -> list[dict]:
    results = []
    for p in programs:
        if not p.get("offers_bounties"):
            continue
        if p.get("submission_state") not in (None, "open"):
            continue
        scope_items = [
            s["asset_identifier"]
            for s in p.get("targets", {}).get("in_scope", [])
            if s.get("eligible_for_bounty") and s.get("asset_identifier")
        ]
        p["_scope_items"] = scope_items
        p["_platform"] = "hackerone"
        results.append(p)
    return results


def parse_bc(programs: list[dict]) -> list[dict]:
    results = []
    for p in programs:
        if not p.get("max_payout") and not p.get("bounty"):
            continue
        scope_items = []
        for t in p.get("targets", []):
            if isinstance(t, dict):
                val = t.get("name") or t.get("target") or t.get("asset_identifier") or ""
                if val:
                    scope_items.append(val)
            elif isinstance(t, str):
                scope_items.append(t)
        p["_scope_items"] = scope_items
        p["_platform"] = "bugcrowd"
        results.append(p)
    return results


# ── Display ───────────────────────────────────────────────────────────────

def print_table(ranked: list[dict], top: int) -> None:
    ranked = ranked[:top]
    print()
    print(f"{'#':<4} {'Score':<7} {'Program':<32} {'Platform':<12} {'Resp':>5} {'Scope':>6}  {'Signals'}")
    print("─" * 95)
    for i, r in enumerate(ranked, 1):
        signals = ", ".join(r["signals"]) if r["signals"] else "—"
        resp = f"{r['response_days']:.0f}d" if r["response_days"] else "—"
        managed = "★" if r["managed"] else " "
        print(
            f"{i:<4} {r['total_score']:<7} {managed}{r['name'][:31]:<32} "
            f"{r['platform']:<12} {resp:>5} {r['scope_count']:>6}  {signals}"
        )
    print()
    print("★ = managed program   Resp = avg first response time   Scope = bounty-eligible assets")
    print()
    print("Next steps:")
    print("  See breakdown:  python scripts/select_program.py --detail 'Program Name'")
    print("  Add to DB:      python scripts/trigger_onboarding.py (coming soon)")


def print_detail(ranked: list[dict], name: str) -> None:
    matches = [r for r in ranked if name.lower() in r["name"].lower()]
    if not matches:
        print(f"\nNo program matching '{name}' found. Try a partial name.")
        return
    for r in matches[:3]:
        print()
        print(f"  ── {r['name']} ({r['platform']}) {'[managed]' if r['managed'] else ''}")
        print(f"  URL:         {r['url']}")
        resp_str = f"{r['response_days']:.0f} days avg" if r['response_days'] else "unknown"
        eff_str = f"{r['efficiency']}%" if r['efficiency'] else "unknown"
        print(f"  Response:    {resp_str}")
        print(f"  Efficiency:  {eff_str}")
        print(f"  Scope items: {r['scope_count']} bounty-eligible")
        print(f"  Signals:     {', '.join(r['signals']) if r['signals'] else '—'}")
        print()
        print(f"  Total score:        {r['total_score']}")
        print(f"    Payout     (20%):  {r['payout_score']}")
        print(f"    Scope      (20%):  {r['scope_score']}")
        print(f"    Competition(25%):  {r['competition_score']}")
        print(f"    Fit        (25%):  {r['fit_score']}")
        print(f"    Momentum   (10%):  {r['momentum_score']}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Score and rank bug bounty programs")
    parser.add_argument("--platform", choices=["h1", "bc", "all"], default="all")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--detail", type=str, help="Show score breakdown for a program")
    args = parser.parse_args()

    platforms = ["h1", "bc"] if args.platform == "all" else [args.platform]

    print()
    print("==> Bug Bounty Program Scorer")
    print()

    all_programs: list[dict] = []
    for key in platforms:
        raw = fetch(SOURCES[key]["url"])
        if not raw:
            continue
        parsed = parse_h1(raw) if key == "h1" else parse_bc(raw)
        print(f"  {SOURCES[key]['name']}: {len(parsed)} programs with active bounties")
        all_programs.extend(parsed)

    if not all_programs:
        print("\nNo programs fetched. Check your internet connection.")
        sys.exit(1)

    print(f"\n  Scoring {len(all_programs)} programs ...")
    ranked = sorted(
        [score_program(p) for p in all_programs],
        key=lambda x: x["total_score"],
        reverse=True,
    )

    if args.detail:
        print_detail(ranked, args.detail)
    else:
        print_table(ranked, args.top)


if __name__ == "__main__":
    main()
