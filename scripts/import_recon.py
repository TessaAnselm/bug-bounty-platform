#!/usr/bin/env python3
"""
Import recon output from Kali/Parrot VM into the local database.

Supports these tool output formats (auto-detected):
    subfinder  -oJ flag  (JSON, one object per line)
    httpx      -json flag (JSON, one object per line)
    katana     -json flag (JSON, one object per line)
    gau / plain text     (one URL or domain per line)

Usage:
    # List programs in your database
    python scripts/import_recon.py --list

    # Import a single file (format auto-detected)
    python scripts/import_recon.py --program <name-or-id> --file results.json

    # Import all files in a directory
    python scripts/import_recon.py --program <name-or-id> --dir /shared/recon/

    # Dry run — shows what would be imported without writing to DB
    python scripts/import_recon.py --program <name-or-id> --file results.json --dry-run

On your VM, save output like this:
    subfinder -d kong.com -oJ -o subfinder.json
    httpx -l subfinder.json -json -o httpx.json
    katana -u https://kong.com -json -o katana.json
    gau kong.com > gau.txt

Then copy the files to your shared folder and run this script on the Mac.
"""

import argparse
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.db.session import engine
from src.db.models import Program, Asset, Alert, AssetType, AssetStatus
from src.activities.storage.scope import validate_target


# ── Format detection ──────────────────────────────────────────────────────

def _detect_format(lines: list[str]) -> str:
    """
    Sniff the first non-empty JSON line to identify which tool produced the file.
    Falls back to 'plain' for plain-text files (one domain/URL per line).
    """
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if "request" in obj and "response" in obj:
                return "katana"
            if "status_code" in obj and "url" in obj:
                return "httpx"
            if "host" in obj and "input" in obj:
                return "subfinder"
        except json.JSONDecodeError:
            pass
        return "plain"
    return "plain"


# ── Per-format parsers ────────────────────────────────────────────────────
# Each parser returns a list of dicts:
# { value, type, http_status, technologies }

def _parse_subfinder(lines: list[str]) -> list[dict]:
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            host = obj.get("host", "").strip()
        except json.JSONDecodeError:
            host = line
        if host:
            results.append({"value": host, "type": AssetType.subdomain,
                             "http_status": None, "technologies": []})
    return results


def _parse_httpx(lines: list[str]) -> list[dict]:
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = obj.get("url", "").strip()
        if not url:
            continue
        tech = obj.get("tech", []) or obj.get("technologies", []) or []
        results.append({
            "value": url,
            "type": AssetType.url,
            "http_status": obj.get("status_code"),
            "technologies": tech if isinstance(tech, list) else [tech],
        })
    return results


def _parse_katana(lines: list[str]) -> list[dict]:
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        endpoint = (obj.get("request") or {}).get("endpoint", "").strip()
        if not endpoint:
            continue
        status = (obj.get("response") or {}).get("status_code")
        asset_type = AssetType.api_endpoint if "/api" in endpoint else AssetType.url
        results.append({"value": endpoint, "type": asset_type,
                         "http_status": status, "technologies": []})
    return results


def _parse_plain(lines: list[str]) -> list[dict]:
    results = []
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.startswith("http"):
            asset_type = AssetType.api_endpoint if "/api" in value else AssetType.url
        else:
            asset_type = AssetType.subdomain
        results.append({"value": value, "type": asset_type,
                         "http_status": None, "technologies": []})
    return results


PARSERS = {
    "subfinder": _parse_subfinder,
    "httpx": _parse_httpx,
    "katana": _parse_katana,
    "plain": _parse_plain,
}


# ── Database helpers ──────────────────────────────────────────────────────

def _find_program(session: Session, name_or_id: str) -> Program | None:
    """Look up a program by UUID or partial name match."""
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


def _upsert_asset(session: Session, program: Program, item: dict, dry_run: bool) -> str:
    """
    Insert a new asset or update last_seen on an existing one.
    Returns: 'new', 'updated', 'skipped' (out of scope)
    """
    scope = program.scope or []
    out_of_scope = program.out_of_scope or []

    # Strip protocol for scope check (validate_target handles domains)
    check_value = item["value"]
    if not validate_target(check_value, scope, out_of_scope):
        return "skipped"

    if dry_run:
        return "new"

    existing = session.execute(
        select(Asset)
        .where(Asset.program_id == program.id)
        .where(Asset.value == item["value"])
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing:
        existing.last_seen = now
        existing.is_new = False
        if item["http_status"]:
            existing.http_status = item["http_status"]
        if item["technologies"]:
            existing.technologies = item["technologies"]
        return "updated"

    asset = Asset(
        program_id=program.id,
        type=item["type"],
        value=item["value"],
        status=AssetStatus.active,
        http_status=item["http_status"],
        technologies=item["technologies"] or [],
        ports=[],
        is_new=True,
        first_seen=now,
        last_seen=now,
    )
    session.add(asset)

    alert = Alert(
        program_id=program.id,
        type="new_asset",
        message=f"New asset discovered (imported): {item['value']}",
        seen=False,
    )
    session.add(alert)

    return "new"


# ── File processing ───────────────────────────────────────────────────────

def process_file(filepath: Path, program: Program, dry_run: bool) -> dict:
    lines = filepath.read_text(errors="replace").splitlines()
    fmt = _detect_format(lines)
    items = PARSERS[fmt](lines)

    counts = {"new": 0, "updated": 0, "skipped": 0, "total": len(items)}

    with Session(engine) as session:
        for item in items:
            result = _upsert_asset(session, program, item, dry_run)
            counts[result] += 1
        if not dry_run:
            session.commit()

    return {"file": filepath.name, "format": fmt, **counts}


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Import VM recon output into the platform")
    parser.add_argument("--list", action="store_true", help="List available programs")
    parser.add_argument("--program", help="Program name or UUID")
    parser.add_argument("--file", help="Single file to import")
    parser.add_argument("--dir", help="Directory of files to import")
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

    if not args.file and not args.dir:
        print("ERROR: provide --file or --dir.")
        sys.exit(1)

    with Session(engine) as session:
        program = _find_program(session, args.program)

    if not program:
        print(f"ERROR: Program '{args.program}' not found. Use --list to see available programs.")
        sys.exit(1)

    files: list[Path] = []
    if args.file:
        files.append(Path(args.file))
    if args.dir:
        files.extend(Path(args.dir).glob("*"))
        files = [f for f in files if f.is_file() and not f.name.startswith(".")]

    if not files:
        print("No files found.")
        sys.exit(1)

    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Importing into: {program.name} ({program.platform})")
    print(f"  Scope: {len(program.scope or [])} patterns  |  "
          f"Out-of-scope: {len(program.out_of_scope or [])} patterns")
    if args.dry_run:
        print("  (dry run — nothing will be written)\n")
    else:
        print()

    totals = {"new": 0, "updated": 0, "skipped": 0, "total": 0}

    for filepath in sorted(files):
        result = process_file(filepath, program, args.dry_run)
        print(f"  {result['file']:<30} [{result['format']:<10}]  "
              f"new: {result['new']:<5} updated: {result['updated']:<5} "
              f"skipped: {result['skipped']:<5} / {result['total']}")
        for key in totals:
            totals[key] += result[key]

    print()
    print(f"  Total:  new={totals['new']}  updated={totals['updated']}  "
          f"skipped={totals['skipped']} (out of scope)  parsed={totals['total']}")

    if not args.dry_run and totals["new"] > 0:
        print(f"\n  {totals['new']} new assets added — check the dashboard for alerts.")
    print()


if __name__ == "__main__":
    main()
