#!/usr/bin/env python3
"""
Fetch passive OSINT data from public sources into the platform database.

All sources here are passive — they query existing public data and never touch
the target directly. This keeps us inside the rules of engagement for every
program, even those that ban active scanning.

Sources:
  crt.sh          Certificate Transparency logs — free, no auth needed
  urlscan         URLScan.io passive URL data — requires URLSCAN_API_KEY in .env
  github          GitHub code search for domain references — requires GITHUB_TOKEN in .env
  securitytrails  Subdomain enumeration via DNS history — requires SECURITYTRAILS_API_KEY in .env
  whoxy           Reverse WHOIS to find related domains — requires WHOXY_API_KEY in .env

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
  crt.sh          → subdomains stored as assets in DB
  urlscan         → URLs stored as assets in DB
  github          → repo/file references printed only (manual review needed)
  securitytrails  → subdomains stored as assets in DB
  whoxy           → related domains printed only (manual review — likely out of scope)
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

# API keys loaded from .env — each source silently skips if its key is absent
URLSCAN_API_KEY = os.getenv("URLSCAN_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
SECURITYTRAILS_API_KEY = os.getenv("SECURITYTRAILS_API_KEY", "")
WHOXY_API_KEY = os.getenv("WHOXY_API_KEY", "")

_TIMEOUT = 30  # seconds — generous for slow CT/WHOIS APIs


# ── Domain extraction ─────────────────────────────────────────────────────────

def _extract_domains(scope: list[str]) -> list[str]:
    """
    Extract bare hostnames from program scope patterns for use as API query targets.

    Scope entries can be wildcards (*.example.com), full URLs (https://api.example.com/v2),
    or plain domains. OSINT APIs expect a bare domain like 'example.com', so we strip
    everything that isn't the hostname portion.
    """
    domains = []
    for pattern in scope:
        pattern = re.sub(r'^https?://', '', pattern)  # drop protocol
        pattern = pattern.lstrip('*.')                 # drop wildcard prefix
        pattern = pattern.split('/')[0]                # drop path
        pattern = pattern.split(':')[0]                # drop port
        if pattern and '.' in pattern:
            domains.append(pattern)
    return list(dict.fromkeys(domains))  # deduplicate while preserving order


# ── crt.sh ────────────────────────────────────────────────────────────────────

def fetch_crtsh(domain: str) -> list[str]:
    """
    Query Certificate Transparency logs via crt.sh to enumerate subdomains.

    CT logs record every TLS certificate ever issued. Every subdomain that has
    ever had HTTPS — including staging, dev, and internal — appears here, making
    this the highest-coverage passive subdomain source that requires no API key.

    The '%.domain' wildcard in the query matches any subdomain depth.
    """
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
        # name_value can be newline-separated when a cert covers multiple SANs
        for name in entry.get("name_value", "").split("\n"):
            name = name.strip().lstrip("*.")
            if name and "." in name and not name.startswith("@") and domain in name:
                names.add(name.lower())

    return sorted(names)


# ── URLScan ───────────────────────────────────────────────────────────────────

def fetch_urlscan(domain: str) -> list[str]:
    """
    Query URLScan.io for URLs crawled under a domain.

    URLScan stores full page URLs including paths and parameters from passive
    browser scans submitted by the community. This surfaces API endpoints,
    admin paths, and versioned routes that subdomain enumeration alone misses.

    Requires URLSCAN_API_KEY in .env (free tier available).
    """
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
    """
    Search GitHub public code for files referencing the target domain.

    Developers often hardcode internal endpoints, API base URLs, and environment
    configs in public repos — including the company's own open-source projects.
    This surfaces endpoints, tokens, and internal hosts that never appear in DNS.

    Results are printed for manual review only, not stored automatically, because
    they need human judgment to determine relevance and in-scope status.

    Requires GITHUB_TOKEN in .env (free, just needs a personal access token).
    """
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


# ── SecurityTrails ────────────────────────────────────────────────────────────

def fetch_securitytrails(domain: str) -> list[str]:
    """
    Query SecurityTrails for subdomains via historical DNS record data.

    SecurityTrails maintains a historical DNS database that captures subdomains
    even after they've been removed from active DNS — useful for finding
    decommissioned staging environments or forgotten assets still running.
    Complements crt.sh which is certificate-based rather than DNS-based.

    Free tier: 50 queries/month. Requires SECURITYTRAILS_API_KEY in .env.
    """
    if not SECURITYTRAILS_API_KEY:
        print("    securitytrails: SECURITYTRAILS_API_KEY not set in .env — skipping")
        return []

    try:
        resp = requests.get(
            f"https://api.securitytrails.com/v1/domain/{domain}/subdomains",
            headers={"APIKEY": SECURITYTRAILS_API_KEY},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    securitytrails error for {domain}: {e}")
        return []

    # API returns bare labels ("www", "api") — we reconstruct FQDNs
    subdomains = []
    for sub in data.get("subdomains", []):
        subdomains.append(f"{sub}.{domain}")

    return sorted(subdomains)


# ── Whoxy ─────────────────────────────────────────────────────────────────────

def fetch_whoxy(domain: str) -> list[dict]:
    """
    Reverse WHOIS pivot via Whoxy — finds other domains registered by the same entity.

    Two-step technique:
      1. WHOIS lookup on the target domain → extract the registrant email address.
      2. Reverse WHOIS by that email → find every other domain the same person or
         company has ever registered.

    This surfaces sibling brands, acquisitions, internal tooling domains, and
    shadow IT that the bug bounty program may not have listed in scope yet. It's
    also useful for finding a company's test or staging TLDs (.dev, .internal,
    .io variants) that share infrastructure with the main product.

    Results are printed for manual review only, NOT stored automatically — these
    domains are almost always out of scope and need human judgment before testing.

    Requires WHOXY_API_KEY in .env (pay-per-query, ~$2 per 5000 queries).
    """
    if not WHOXY_API_KEY:
        print("    whoxy: WHOXY_API_KEY not set in .env — skipping")
        return []

    # Step 1: WHOIS lookup to get registrant contact details
    try:
        resp = requests.get(
            "https://api.whoxy.com/",
            params={"key": WHOXY_API_KEY, "whois": domain},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        whois_data = resp.json()
    except Exception as e:
        print(f"    whoxy WHOIS error for {domain}: {e}")
        return []

    registrant = whois_data.get("registrant_contact", {})
    email = registrant.get("email_address", "").strip()
    company = registrant.get("company_name", "").strip()

    if not email or "@" not in email:
        # Privacy-protected WHOIS (e.g. via registrar proxy) returns no email
        print(f"    whoxy: no registrant email found for {domain} — skipping reverse WHOIS")
        return []

    # Step 2: Reverse WHOIS — find all domains registered by this email
    try:
        resp = requests.get(
            "https://api.whoxy.com/",
            params={"key": WHOXY_API_KEY, "reverse": "whois", "email": email, "mode": "mini"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        reverse_data = resp.json()
    except Exception as e:
        print(f"    whoxy reverse WHOIS error: {e}")
        return []

    results = []
    for entry in reverse_data.get("search_result", []):
        related = entry.get("domain_name", "").strip().lower()
        if related and related != domain and "." in related:
            results.append({
                "domain": related,
                "registrant_email": email,
                "registrant_company": company,
            })

    return results


# ── DB helpers ────────────────────────────────────────────────────────────────

def _find_program(session: Session, name_or_id: str):
    """
    Look up a program by UUID or partial name match.

    Accepts either the full UUID (unambiguous) or a case-insensitive substring
    of the program name. If multiple programs match the partial name, prints
    all matches and returns None so the caller can prompt for a full ID.
    """
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
    """
    Insert a new asset or refresh an existing one, enforcing scope boundaries.

    Returns 'new', 'updated', or 'skipped' so the caller can track counts.

    Why we calculate risk and tags here rather than later: doing it at import
    time means the asset is immediately sortable in the triage queue without
    requiring a separate scoring pass. Risk score and tags are recalculated on
    each update so they stay current as the asset evolves.
    """
    scope = program.scope or []
    out_of_scope = program.out_of_scope or []

    # Hard gate — never store an asset that falls outside the program's declared scope
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
        # Refresh metadata but don't re-flag as new — it's already been seen
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
    # Fire an alert so the dashboard highlights this asset for review
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
                        choices=["all", "crt.sh", "urlscan", "github", "securitytrails", "whoxy"],
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

    # All OSINT sources are passive reads from public data — they are always
    # allowed regardless of the program's active-scanning constraint.

    # Determine which domains to query: explicit override or extracted from scope
    if args.domain:
        domains = [args.domain]
    else:
        domains = _extract_domains(program.scope or [])
        if not domains:
            print("ERROR: No domains could be extracted from scope. Use --domain to specify one.")
            sys.exit(1)

    # Resolve which sources to run based on --source flag
    run_crtsh          = args.source in ("all", "crt.sh")
    run_urlscan        = args.source in ("all", "urlscan")
    run_github         = args.source in ("all", "github")
    run_securitytrails = args.source in ("all", "securitytrails")
    run_whoxy          = args.source in ("all", "whoxy")

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Program: {program.name} ({program.platform})")
    print(f"  Domains: {', '.join(domains)}")
    print(f"  Sources: {args.source}")
    if args.dry_run:
        print("  (dry run — nothing will be written)\n")
    else:
        print()

    # Counts tracked across all domains for the summary line at the end
    totals = {"new": 0, "updated": 0, "skipped": 0}

    for domain in domains:
        print(f"  [{domain}]")

        if run_crtsh:
            print(f"    crt.sh          ...", end=" ", flush=True)
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
            print(f"    urlscan         ...", end=" ", flush=True)
            urls = fetch_urlscan(domain)
            counts = {"new": 0, "updated": 0, "skipped": 0}
            with Session(engine) as session:
                for url in urls:
                    # URLs containing /api/ are stored as api_endpoint for better triage tagging
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
            print(f"    github          ...", end=" ", flush=True)
            refs = fetch_github(domain)
            print(f"found {len(refs)} references (manual review — not stored)")
            if refs:
                for r in refs[:10]:
                    print(f"      {r['repo']}  {r['file']}")
                    print(f"        {r['url']}")
                if len(refs) > 10:
                    print(f"      ... and {len(refs) - 10} more")
            time.sleep(1)

        if run_securitytrails:
            print(f"    securitytrails  ...", end=" ", flush=True)
            subdomains = fetch_securitytrails(domain)
            counts = {"new": 0, "updated": 0, "skipped": 0}
            with Session(engine) as session:
                for sub in subdomains:
                    r = _upsert(session, program, sub, AssetType.subdomain, "securitytrails", args.dry_run)
                    counts[r] += 1
                if not args.dry_run:
                    session.commit()
            print(f"found {len(subdomains)}  new:{counts['new']} updated:{counts['updated']} skipped:{counts['skipped']}")
            for k in totals:
                totals[k] += counts[k]
            time.sleep(1)

        if run_whoxy:
            print(f"    whoxy           ...", end=" ", flush=True)
            related = fetch_whoxy(domain)
            print(f"found {len(related)} related domains (manual review — not stored)")
            if related:
                registrant = related[0].get("registrant_company") or related[0].get("registrant_email", "")
                print(f"      Registrant: {registrant}")
                for r in related[:15]:
                    print(f"      {r['domain']}")
                if len(related) > 15:
                    print(f"      ... and {len(related) - 15} more")
            time.sleep(1)

        print()

    print(f"  Total assets:  new={totals['new']}  updated={totals['updated']}  skipped={totals['skipped']} (out of scope)")
    if not args.dry_run and totals["new"] > 0:
        print(f"\n  {totals['new']} new assets added — check the dashboard for alerts.")
    print()


if __name__ == "__main__":
    main()
