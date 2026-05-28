"""
Trigger a ReconWorkflow for an already-onboarded program.

Kong was onboarded directly through the dashboard (not via ProgramOnboardingWorkflow),
so this script is how we kick off recon manually. It submits a ReconWorkflow to
Temporal, which the worker picks up and executes step by step:
  subfinder → httpx → (katana + gowitness + gau + github) → store → diff → alert

Usage:
  .venv/bin/python scripts/trigger_recon.py --list
  .venv/bin/python scripts/trigger_recon.py --program "Kong"
  .venv/bin/python scripts/trigger_recon.py --program "Kong" --dry-run

Monitor progress:
  Temporal UI  → http://localhost:8080  (live activity-by-activity view)
  Worker log   → tail -f logs/worker.log
  Dashboard    → http://localhost:8000  → Health page (recon run record)
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from temporalio.client import Client
from sqlalchemy.orm import Session
from sqlalchemy import select

# Allow running from the project root without installing the package as a module.
# Without this, `from src.db...` imports fail because Python doesn't know where
# the project root is when the script is invoked directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before importing src modules — DATABASE_URL and TEMPORAL_HOST are
# read at import time by session.py and would be missing without this.
load_dotenv()

from src.db.session import engine
from src.db.models import Program
from src.db.models.program import ProgramStatus
from src.workflows.recon import ReconWorkflow
from src.workflows.types import ReconInput


def _list_programs() -> None:
    """Print all programs with their current status and IDs.

    Why: before triggering recon you need the exact program name (used for
    fuzzy lookup in _get_program). This gives you a quick overview without
    opening the dashboard.
    """
    with Session(engine) as session:
        programs = session.execute(
            select(Program).order_by(Program.created_at.desc())
        ).scalars().all()
        if not programs:
            print("No programs found. Onboard one from the dashboard first.")
            return
        print(f"{'Name':<30} {'Status':<10} {'ID'}")
        print("-" * 75)
        for p in programs:
            print(f"{p.name:<30} {p.status.value:<10} {p.id}")


def _get_program(name: str) -> Program | None:
    """Look up a program by partial name match (case-insensitive).

    Why partial match: avoids requiring the user to type the exact program name
    with correct casing. If multiple programs match (e.g. "Kong" matches both
    "Kong" and "Kong Gateway"), we print all matches and ask for a clearer name
    rather than guessing.

    The object is expunged from the session so it remains usable after the
    session closes — SQLAlchemy lazy-loads would fail on a detached instance
    without this.
    """
    with Session(engine) as session:
        result = session.execute(
            select(Program).where(Program.name.ilike(f"%{name}%"))
        ).scalars().all()
        if not result:
            return None
        if len(result) > 1:
            print(f"Multiple programs match '{name}':")
            for p in result:
                print(f"  {p.name} ({p.id})")
            print("Use a more specific name.")
            return None
        session.expunge(result[0])
        return result[0]


async def trigger(program_name: str, dry_run: bool) -> None:
    """Validate the program and submit a ReconWorkflow to Temporal.

    Why we validate before submitting:
    - Status must be active: ReconWorkflow's first activity (load_program_scope)
      will also reject non-active programs, but failing here gives a cleaner
      error message before any Temporal overhead.
    - Scope must be non-empty: an empty scope means validate_target() rejects
      every discovered asset, so the run would complete with 0 assets stored —
      a waste of a scan.

    Why a timestamped workflow ID: Temporal requires workflow IDs to be unique.
    Using the program name + UTC timestamp lets you run recon multiple times
    (e.g. daily) without ID collisions, and makes it easy to find a specific
    run in the Temporal UI by date.

    Why triggered_by="manual": the ReconRun record in the DB stores who or what
    triggered the scan. "manual" distinguishes this from runs started by
    MonitorWorkflow (which sets triggered_by="monitor") so you can see in the
    Health dashboard which runs were automated vs intentional.
    """
    program = _get_program(program_name)
    if not program:
        print(f"Program '{program_name}' not found. Run --list to see available programs.")
        sys.exit(1)

    if program.status != ProgramStatus.active:
        print(f"Error: '{program.name}' is {program.status.value}. Only active programs can be scanned.")
        sys.exit(1)

    scope_count = len(program.scope or [])
    oos_count = len(program.out_of_scope or [])

    print(f"Program:    {program.name}")
    print(f"Platform:   {program.platform}")
    print(f"Status:     {program.status.value}")
    print(f"Scope:      {scope_count} items")
    print(f"OOS:        {oos_count} items")
    print()

    if scope_count == 0:
        print("Error: program has no scope defined. Add scope from the dashboard first.")
        sys.exit(1)

    workflow_id = (
        f"recon-{program.name.lower().replace(' ', '-')}"
        f"-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    )

    if dry_run:
        # Show what would be submitted without touching Temporal.
        # Always run --dry-run first to confirm scope count looks right
        # before burning a real scan on a misconfigured program.
        print(f"[dry-run] Would submit workflow: {workflow_id}")
        print(f"[dry-run] ReconInput: program_id={program.id}, triggered_by=manual")
        return

    host = os.getenv("TEMPORAL_HOST", "localhost")
    port = os.getenv("TEMPORAL_PORT", "7233")
    client = await Client.connect(f"{host}:{port}")

    handle = await client.start_workflow(
        ReconWorkflow.run,
        ReconInput(program_id=str(program.id), triggered_by="manual"),
        id=workflow_id,
        task_queue="bounty-task-queue",
    )

    print(f"Recon started!")
    print(f"  Workflow ID: {handle.id}")
    print()
    print(f"  Watch live: http://localhost:8080/namespaces/default/workflows/{handle.id}")
    print(f"  Worker log: tail -f logs/worker.log")
    print(f"  Dashboard:  http://localhost:8000  → Health")


def main() -> None:
    """Entry point — parse args and route to list or trigger."""
    parser = argparse.ArgumentParser(description="Trigger a recon workflow for an onboarded program")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all programs")
    group.add_argument("--program", metavar="NAME", help="Program name to run recon on")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without submitting")
    args = parser.parse_args()

    if args.list:
        _list_programs()
    else:
        asyncio.run(trigger(args.program, args.dry_run))


if __name__ == "__main__":
    main()
