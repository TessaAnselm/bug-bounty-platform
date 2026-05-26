#!/usr/bin/env python3
"""
Fetch passive OSINT data from public sources into the platform database.

Sources:
  crt.sh    Certificate Transparency logs — free, no auth needed
  urlscan   URLScan.io passive URL data — requires URLSCAN_API_KEY in .env
  github    GitHub code search for domain references — requires GITHUB_TOKEN in .env

Usage:
  # List programs
  python scripts/fetch_osint.py --list

  # Fetch all sources for a program (domains extracted from scope)
  python scripts/fetch_osint.py --program <name-or-id> --source all

  # Fetch only crt.sh
  python scripts/fetch_osint.py --program <name-or-id> --source crt.sh

  # Fetch for a specific domain
  python scripts/fetch_osint.py --program <name-or-id> --source all --domain api.example.com

  # Dry run — show what would be imported without writing to DB
  python scripts/fetch_osint.py --program <name-or-id> --source all --dry-run

Output:
  crt.sh   → subdomains stored as assets in DB
  urlscan  → URLs stored as assets in DB
  github   → repo/file references printed only (manual review needed)
"""

import argparse
import re
import sys
import time
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import os
import requests
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.db.session import engine
from src.db.models import Program, Asset, Alert, AssetType, AssetStatus
from src.activities.storage.scope import validate_target
from src.activities.scoring.risk import calculate_risk_score, auto_tag

URLSCAN_API_KEY = os.getenv("URLSCAN_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

_TIMEOUT = 30


# ── Domain extraction ─────────────────────────────────────────────────────────

def _extract_domains(scope: list[str]) -> list[str]:
    """Extract base domains from scope patterns like *.example.com or https://api.example.com."""
    domains = []
    for pattern in scope:
        # Strip protocol
        pattern = re.sub(r'^https?://', '', pattern)
        # Strip wildcard prefix
        pattern = pattern.lstrip('*.')
        # Strip path
        pattern = pattern.split('/')[0]
        # Strip port
        pattern = pattern.split(':')[0]
        if pattern and '.' in pattern:
            domains.append(pattern)
    return list(dict.fromkeys(domains))  # deduplicate, preserve order


# ── crt.sh ────────────────────────────────────────────────────────────────────

def fetch_crtsh(domain: str) -> list[str]:
    """Query crt.sh for subdomains via Certificate Transparency logs."""
    try:
        resp = requests.get(
            f"https://crt.sh/?q=%.{domain}&output=json",
            timeout=_TIMEOUT,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    crt.sh error for {domain}: {e}")
        return []

    names: set[str] = set()
    for entry in data:
        for name in entry.get("name_value", "").split("\n"):
            name = name.strip().lstrip("*.")
            if name and "." in name and not name.startswith("@") and domain in name:
                names.add(name.lower())

    return sorted(names)


# ── URLScan ───────────────────────────────────────────────────────────────────

def fetch_urlscan(domain: str) -> list[str]:
    """Query URLScan.io for URLs associated with a domain."""
    if not URLSCAN_API_KEY:
        print("    urlscan: URLSCAN_API_KEY not set in .env — skipping")
        return []

    try:
        resp = requests.get(
            f"https://urlscan.io/api/v1/search/?q=domain:{domain}&size=100",
            headers={"API-Key": URLSCAN_API_KEY},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    urlscan error for {domain}: {e}")
        return []

    urls: set[str] = set()
    for result in data.get("results", []):
        url = result.get("page", {}).get("url", "").strip()
        if url and domain in url:
            urls.add(url)

    return sorted(urls)


# ── GitHub Search ─────────────────────────────────────────────────────────────

def fetch_github(domain: str) -> list[dict]:
    """Search GitHub code for references to the domain. Results are for manual review only."""
    if not GITHUB_TOKEN:
        print("    github: GITHUB_TOKEN not set in .env — skipping")
        return []

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        resp = requests.get(
            f"https://api.github.com/search/code?q={domain}+in:file&per_page=20",
            headers=headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    github error for {domain}: {e}")
        return []

    results = []
    for item in data.get("items", []):
        results.append({
            "repo": item["repository"]["full_name"],
            "file": item["name"],
            "url": item["html_url"],
        })
    return results


# ── DB helpers ────────────────────────────────────────────────────────────────

def _find_program(session: Session, name_or_id: str):
    try:
        uid = UUID(name_or_id)
        return session.get(Program, uid)
    except ValueError:
        pass
    programs = session.execute(select(Program)).scalars().all()
    matches = [p for p in programs if name_or_id.lower() in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"\nAmbiguous name '{name_or_id}' matches:")
        for p in matches:
            print(f"  {p.id}  {p.name}")
        print("Use the full ID instead.")
    return None


def _upsert(session: Session, program, value: str, asset_type: AssetType,
            source: str, dry_run: bool) -> str:
    """Insert or update a single asset. Returns 'new', 'updated', or 'skipped'."""
    scope = program.scope or []
    out_of_scope = program.out_of_scope or []

    if not validate_target(value, scope, out_of_scope):
        return "skipped"

    if dry_run:
        return "new"

    existing = session.execute(
        select(Asset)
        .where(Asset.program_id == program.id)
        .where(Asset.value == value)
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    type_str = asset_type.value
    risk = calculate_risk_score(value, type_str, None, [])
    tags = auto_tag(value, type_str, [])

    if existing:
        existing.last_seen = now
        existing.is_new = False
        existing.risk_score = risk
        existing.tags = tags
        existing.source_tool = source
        return "updated"

    asset = Asset(
        program_id=program.id,
        type=asset_type,
        value=value,
        status=AssetStatus.active,
        http_status=None,
        technologies=[],
        ports=[],
        is_new=True,
        risk_score=risk,
        tags=tags,
        source_tool=source,
        first_seen=now,
        last_seen=now,
    )
    session.add(asset)
    session.add(Alert(
        program_id=program.id,
        type="new_asset",
        message=f"New asset discovered ({source}): {value}",
        seen=False,
    ))
    return "new"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch passive OSINT data into the platform")
    parser.add_argument("--list", action="store_true", help="List available programs")
    parser.add_argument("--program", help="Program name or UUID")
    parser.add_argument("--source", default="all",
                        choices=["all", "crt.sh", "urlscan", "github"],
                        help="Which source to query (default: all)")
    parser.add_argument("--domain", help="Specific domain to query (overrides scope extraction)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be imported without writing to DB")
    args = parser.parse_args()

    if args.list:
        with Session(engine) as session:
            programs = session.execute(select(Program)).scalars().all()
        if not programs:
            print("\nNo programs in database yet.")
        else:
            print(f"\n{'ID':<38} {'Name':<30} {'Status'}")
            print("─" * 75)
            for p in programs:
                print(f"{str(p.id):<38} {p.name:<30} {p.status.value}")
        return

    if not args.program:
        print("ERROR: --program is required. Use --list to see available programs.")
        sys.exit(1)

    with Session(engine) as session:
        program = _find_program(session, args.program)

    if not program:
        print(f"ERROR: Program '{args.program}' not found.")
        sys.exit(1)

    # Check constraints
    constraints = program.constraints or {}
    if not constraints.get("allow_active_scanning", True):
        pass  # OSINT sources are all passive — constraints don't block them

    # Determine domains to query
    if args.domain:
        domains = [args.domain]
    else:
        domains = _extract_domains(program.scope or [])
        if not domains:
            print(f"ERROR: No domains could be extracted from scope. Use --domain to specify one.")
            sys.exit(1)

    run_crtsh = args.source in ("all", "crt.sh")
    run_urlscan = args.source in ("all", "urlscan")
    run_github = args.source in ("all", "github")

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Program: {program.name} ({program.platform})")
    print(f"  Domains: {', '.join(domains)}")
    print(f"  Sources: {args.source}")
    if args.dry_run:
        print("  (dry run — nothing will be written)\n")
    else:
        print()

    totals = {"new": 0, "updated": 0, "skipped": 0}

    for domain in domains:
        print(f"  [{domain}]")

        if run_crtsh:
            print(f"    crt.sh ...", end=" ", flush=True)
            subdomains = fetch_crtsh(domain)
            counts = {"new": 0, "updated": 0, "skipped": 0}
            with Session(engine) as session:
                for sub in subdomains:
                    r = _upsert(session, program, sub, AssetType.subdomain, "crt.sh", args.dry_run)
                    counts[r] += 1
                if not args.dry_run:
                    session.commit()
            print(f"found {len(subdomains)}  new:{counts['new']} updated:{counts['updated']} skipped:{counts['skipped']}")
            for k in totals:
                totals[k] += counts[k]
            time.sleep(1)

        if run_urlscan:
            print(f"    urlscan ...", end=" ", flush=True)
            urls = fetch_urlscan(domain)
            counts = {"new": 0, "updated": 0, "skipped": 0}
            with Session(engine) as session:
                for url in urls:
                    asset_type = AssetType.api_endpoint if "/api" in url else AssetType.url
                    r = _upsert(session, program, url, asset_type, "urlscan", args.dry_run)
                    counts[r] += 1
                if not args.dry_run:
                    session.commit()
            print(f"found {len(urls)}  new:{counts['new']} updated:{counts['updated']} skipped:{counts['skipped']}")
            for k in totals:
                totals[k] += counts[k]
            time.sleep(1)

        if run_github:
            print(f"    github  ...", end=" ", flush=True)
            refs = fetch_github(domain)
            print(f"found {len(refs)} references (manual review — not stored)")
            if refs:
                for r in refs[:10]:
                    print(f"      {r['repo']}  {r['file']}")
                    print(f"        {r['url']}")
                if len(refs) > 10:
                    print(f"      ... and {len(refs) - 10} more")
            time.sleep(1)

        print()

    print(f"  Total assets:  new={totals['new']}  updated={totals['updated']}  skipped={totals['skipped']} (out of scope)")
    if not args.dry_run and totals["new"] > 0:
        print(f"\n  {totals['new']} new assets added — check the dashboard for alerts.")
    print()


if __name__ == "__main__":
    main()
