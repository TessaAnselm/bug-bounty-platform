# Code Architecture

A plain-English guide to where everything lives and what it does.

---

## The Big Picture

This is an ethical bug bounty research platform — a personal hacker lab that runs locally. Companies pay people to find security holes in their software before bad guys do. This platform helps you do that professionally and systematically.

---

## Folder Structure

```
Bug Bounty Project/
│
├── src/                    ← All the Python code (the brains)
│   ├── db/                 ← Database blueprints and connection
│   │   ├── models/         ← The 9 table designs (Program, Asset, Finding...)
│   │   └── session.py      ← How to connect to the database
│   │
│   ├── workflows/          ← The 4 automated workflows (Temporal)
│   │   ├── onboarding.py   ← Adds a new target program
│   │   ├── recon.py        ← Scans for assets automatically
│   │   ├── monitor.py      ← Runs recon on a schedule
│   │   └── finding.py      ← Tracks bugs from discovery to payout
│   │
│   ├── activities/         ← The actual work each workflow does
│   │   ├── recon/          ← Runs subfinder, httpx, screenshots etc.
│   │   ├── storage/        ← Saves results to the database
│   │   ├── scoring/        ← Calculates program scores
│   │   └── notifications/  ← Sends Discord alerts
│   │
│   ├── api/                ← The dashboard website
│   │   ├── routers/        ← Each page (programs, assets, findings...)
│   │   ├── templates/      ← The HTML you see in the browser
│   │   └── static/         ← The dark terminal styling (CSS)
│   │
│   └── mcp/                ← The bridge that lets Claude read your data
│       ├── server.py       ← Main entry point
│       ├── resources/      ← What Claude can read (programs, assets...)
│       └── tools/          ← What Claude can search and summarize
│
├── .github/workflows/      ← CI pipeline (GitHub runs this on every push)
│   └── ci.yml              ← The 4 security checks (gitleaks, Snyk, Semgrep, pytest)
│
├── scripts/                ← Shortcuts to run the platform
│   ├── start.sh            ← One command to start everything
│   └── stop.sh             ← One command to stop worker and dashboard
│
├── tests/                  ← Automated tests
│   └── test_smoke.py       ← 6 tests that verify nothing is broken
│
├── specializations/        ← Your hunting playbooks
│   ├── idor-api/           ← Phase 1 (active) — how to find IDOR and API bugs
│   ├── oauth-auth/         ← Phase 2 — authentication vulnerabilities
│   └── ai-llm/             ← Phase 3 — AI/LLM specific attacks
│
├── core/                   ← Research methodology documents
│   ├── ethics-checklist.md ← Must run before every engagement
│   └── methodology.md      ← 8-step research process
│
├── docker-compose.yml      ← Tells Docker what servers to run
├── requirements.txt        ← All Python packages the code needs
├── CLAUDE.md               ← Context file so Claude remembers this project
└── PROGRESS.md             ← Build tracker (all 6 steps checked off)
```

---

## The 6 Layers

### Layer 1 — Infrastructure (Docker)
Three servers running inside containers on your Mac mini:
- **PostgreSQL** — the database that stores everything
- **Temporal server** — the workflow engine that runs long tasks automatically
- **Temporal UI** — a browser interface to watch workflows run (localhost:8080)

Started with: `docker compose up -d`

### Layer 2 — Database (src/db/)
9 tables that store all platform data:

| Table | What it stores |
|---|---|
| programs | Bug bounty programs you are targeting |
| assets | Domains, subdomains, IPs found during recon |
| findings | Bugs you discovered |
| recon_runs | History of every recon scan |
| alerts | Notifications (new assets, changes) |
| session_notes | Your research notes per asset |
| outcomes | What happened with each finding (paid, rejected) |
| program_scores | Calculated priority scores per program |
| artifacts | Screenshots, Burp exports, PoC files |

### Layer 3 — Workflows (src/workflows/)
4 automated processes that run inside Temporal:

| Workflow | What it does |
|---|---|
| ProgramOnboardingWorkflow | One-time setup when you add a new target |
| ReconWorkflow | Subdomain enum → probe → fingerprint → store → diff → alert |
| MonitorWorkflow | Long-running loop that re-runs recon on a schedule |
| FindingWorkflow | Tracks a bug from discovery through triage to payout |

The worker that runs these is started with: `.venv/bin/python -m src.worker.main`

### Layer 4 — Dashboard (src/api/)
A private website running at `localhost:8000`. Requires an API key to access.

| Page | What you see |
|---|---|
| /programs | All programs with scores and status |
| /assets | All discovered assets, highlighted new ones |
| /findings | Bug pipeline sorted by status (kanban-style) |
| /alerts | Unread alerts |
| /dashboard/health | Recon run history and workflow status |

Started with: `.venv/bin/uvicorn src.api.main:app --reload`

### Layer 5 — AI Interface (src/mcp/)
A read-only bridge that lets Claude Code query your live database. Claude can answer questions like "what new assets did recon find?" or "summarize this program" using your real data.

Registered in `.mcp.json` — Claude Code picks it up automatically on restart.

### Layer 6 — CI Pipeline (.github/workflows/)
4 security checks that run automatically on every git push:

| Check | What it catches |
|---|---|
| gitleaks | Accidentally committed passwords or API keys |
| Snyk Code | Security vulnerabilities in your Python code |
| Semgrep | Additional code security issues |
| pytest | Broken imports or failed smoke tests |

---

## Where It Runs

| Location | Purpose |
|---|---|
| Your Mac mini | Platform runs here — Docker, worker, dashboard |
| GitHub | Code is stored here — CI security checks run on every push |

Nothing is in the cloud. No monthly bills. No external dependencies.

---

## How To Start Everything

```bash
bash scripts/start.sh
```

This starts Docker containers (if not running), the Temporal worker, and the FastAPI dashboard. Prints the dashboard URL with your API key when done.

To stop the worker and dashboard:

```bash
bash scripts/stop.sh
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Workflow engine | Temporal OSS |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Dashboard | FastAPI + Jinja2 |
| AI interface | MCP (Model Context Protocol) |
| Recon tools | subfinder, httpx, katana, gau, gowitness, truffleHog |
| Security scanning | Snyk + Semgrep + gitleaks |
| CI | GitHub Actions |
| Containerization | Docker Compose |
