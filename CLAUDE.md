# Bug Bounty Platform — Claude Code Context

This file is auto-loaded by Claude Code at the start of every session.
It contains everything needed to resume work without re-explaining the design.

---

## What This Project Is

An ethical bug bounty research platform built as a **research notebook**, not an automation platform. Philosophy: depth over breadth — manual testing, logic bugs, and chained vulnerabilities that AI and scanners miss.

**First target:** An authorized public bug bounty program aligned with AI/API security specialization.

---

## Core Design Principles

- **Ethics first** — ethics checklist is a hard gate before any recon workflow starts
- **Research notebook** — understand targets deeply, not spray-and-pray scanning
- **Free stack** — everything open source, runs locally, no API costs
- **AI-agnostic** — MCP server exposes data, Claude Code connects externally (no embedded AI)
- **Depth over breadth** — 1-3 programs at a time, fully mapped

---

## Confirmed Tech Stack

```
Language:       Python 3.12
Workflows:      Temporal OSS (Docker) — 4 core workflows
Database:       PostgreSQL (single DB for app + Temporal)
Dashboard:      FastAPI + Jinja2 HTML + basic API key auth
Notifications:  Discord webhook
AI interface:   Claude Code + local MCP server (read-only, passive)
Platform sec:   Snyk (MCP) + Semgrep + gitleaks
Recon tools:    subfinder, httpx, katana, gau, gowitness, truffleHog
Vuln scanning:  Nuclei (where program permits only)
CI/CD:          GitHub Actions
Infra:          Docker Compose (local), env-var config for future VPS migration
```

---

## Architecture

```
External Sources:
  bounty-targets-data (GitHub, daily cron)
  crt.sh (CT logs, cron)
  GitHub API (on-demand OSINT)

Workflows (Temporal — 4 core):
  ProgramOnboardingWorkflow     one-time per program, triggers recon
  ReconWorkflow                 subdomain enum → probe → fingerprint → store → diff → alert
  MonitorWorkflow               long-running, scheduled, calls ReconWorkflow on interval
  FindingWorkflow               human-in-loop, tracks finding lifecycle via signals

Storage:
  PostgreSQL:   programs, assets, findings, alerts, session_notes,
                recon_runs, outcomes, program_scores
  Filesystem:   artifacts/ (screenshots, burp exports, PoCs) — gitignored
                exports/ (generated reports) — gitignored

Interfaces:
  FastAPI dashboard   your hunting view (program list, assets, finding pipeline)
  Temporal UI         infra/workflow health view
  MCP server          read-only — Claude Code queries programs, assets, findings,
                      alerts, session_notes, recon_runs, program_scores
```

---

## Data Model (Key Tables)

```
programs        id, name, platform, scope(jsonb), out_of_scope(jsonb),
                max_payout, status, created_at

assets          id, program_id, type, value, status, technologies(jsonb),
                ports(jsonb), screenshot_path, http_status, first_seen,
                last_seen, is_new

findings        id, program_id, asset_id, title, vuln_type, severity,
                status, report_url, payout_amount, submitted_at,
                triaged_at, resolved_at, paid_at, temporal_workflow_id

recon_runs      id, program_id, temporal_workflow_id, status,
                triggered_by, assets_found, new_assets, started_at,
                completed_at

alerts          id, program_id, asset_id, type, message, seen, created_at

session_notes   id, program_id, asset_id, content(markdown), created_at

outcomes        id, finding_id, result, payout_amount, time_spent_hours,
                lessons, recorded_at

program_scores  id, program_id, total_score, payout_score, scope_score,
                competition_score, fit_score, momentum_score,
                top_signals(jsonb), scored_at, scoring_version

artifacts       id, finding_id, asset_id, type, path, created_at
```

---

## Specializations (Phased)

```
Phase 1 (active):    IDOR + API Security       → fastest path to first paid bug
Phase 2:             OAuth + Authentication     → add after first paid finding
Phase 3:             AI/LLM Security            → add after Phase 2
Phase 4 (future):    Web3 / Smart Contracts     → placeholder, requires Solidity
```

Content lives in `specializations/{idor-api,oauth-auth,ai-llm}/` — each has
methodology.md, checklist.md, tools.md, resources.md.

---

## Program Scoring Model

Five dimensions, each 0–100:

```
Payout Score      (20%)   max payout, avg historical, consistency
Scope Score       (20%)   wildcard domains, asset type breadth, restrictions
Competition Score (25%)   program age, recent disclosures, platform traffic
Fit Score         (25%)   specialization match, tech stack, vertical interest
Momentum Score    (10%)   recent scope additions, new program, acquisitions
```

Fit score bonuses: AI/LLM features (+35), API scope (+30), OAuth/SSO (+25),
cloud assets (+15), mobile (+10). AI/ML vertical multiplier: 1.3x.

Score improves over time from outcomes table (what signals predicted real findings).

---

## V1 Build Order (Current Focus)

```
Step 1:   Docker Compose + Temporal + PostgreSQL setup
Step 2:   DB schema + Alembic migrations
Step 3:   Python Temporal workers + 4 core workflows
Step 4:   FastAPI dashboard (program, asset, finding views)
Step 5:   MCP server (read-only resources)
Step 6:   CI pipeline (gitleaks + Snyk + Semgrep)
```

See PROGRESS.md for current step and status.

---

## V2 Features (After First Paid Finding)

Program discovery (bounty-targets-data), full scoring model, platform API sync
(HackerOne/Bugcrowd), CT log monitoring, outcomes/feedback loop, report export
pipeline, artifact storage.

---

## Security Notes

- `targets/` and `reports/` are gitignored — never commit findings
- `artifacts/` and `exports/` are gitignored — never commit evidence
- `.env` is gitignored — never commit credentials
- Dashboard requires API key auth (key in .env)
- Snyk MCP is already wired in this session — run on all new code
- Run gitleaks before every commit

---

## MCP Server Resources (Read-Only)

```
programs          list, get by id
assets            list by program, filter by is_new, type, status
findings          list by program, list by status
recon_runs        latest per program, history
alerts            unseen count, list
session_notes     by program, by asset
program_scores    ranked list, get by program
```

---

## Key Files

```
CLAUDE.md                     this file — session context
PROGRESS.md                   current build status and next action
core/methodology.md           universal 8-step research process
core/ethics-checklist.md      run before every engagement
core/report-template.md       standard report structure
core/program-selection.md     how to pick programs
specializations/idor-api/     Phase 1 specialization (active)
specializations/oauth-auth/   Phase 2 specialization
specializations/ai-llm/       Phase 3 specialization
```
