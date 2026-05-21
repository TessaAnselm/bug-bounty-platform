# Bug Bounty Research Platform

A personal, structured platform for ethical bug bounty research. Built as a research notebook with automated recon, finding lifecycle tracking, and AI-assisted triage — not an autonomous exploitation engine.

## Philosophy

Depth over breadth. Understanding targets well enough to find what automated tools miss — logic flaws, broken authorization, and chained vulnerabilities that require human reasoning.

## Status

**V1 Complete — Ready to Hunt.**

All 6 build steps finished. Platform is live locally with Docker, CI passing on every push.

See [PROGRESS.md](PROGRESS.md) for full build history.

---

## Safety First

This platform is built with human-in-the-loop design at every layer:

- **Ethics checklist** required before any program goes active
- **Scope enforcement** — `validate_target()` filters out-of-scope assets before storage
- **No autonomous exploitation** — recon only, all findings require human review
- **Confidence scoring** — every finding carries a human-assigned confidence score (0–100%)

See [SECURITY.md](SECURITY.md), [ETHICS.md](ETHICS.md), and [SCOPE_POLICY.md](SCOPE_POLICY.md) for full details.

---

## Stack

Built entirely on free and open source tools. Runs locally — no cloud, no monthly bills.

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Workflow engine | Temporal OSS |
| Database | PostgreSQL 15 |
| Dashboard | FastAPI + Jinja2 |
| AI interface | Claude Code + MCP server (read-only) |
| Recon tools | subfinder, httpx, katana, gau, gowitness, truffleHog |
| Security scanning | Snyk + Semgrep + gitleaks |
| CI | GitHub Actions |
| Infra | Docker Compose (local) |

---

## Architecture

```
Recon Tools (subfinder, httpx, katana, gau, gowitness, truffleHog)
        ↓
Temporal Workflows (4 core: Onboarding, Recon, Monitor, Finding)
        ↓
PostgreSQL (9 tables: programs, assets, findings, alerts, notes, scores...)
        ↓
FastAPI Dashboard (localhost:8000) + MCP Server (Claude Code reads live data)
        ↓
CI Pipeline (gitleaks + Snyk + Semgrep + pytest on every push)
```

---

## Quick Start

```bash
# Start everything
bash scripts/start.sh

# Stop worker and dashboard (leaves Docker running)
bash scripts/stop.sh
```

Dashboard: `http://localhost:8000?api_key=YOUR_KEY`
Temporal UI: `http://localhost:8080`

---

## Structure

```
src/workflows/      4 Temporal workflows (onboarding, recon, monitor, finding)
src/activities/     Activities: recon tools, storage, scoring, notifications
src/api/            FastAPI dashboard + templates
src/mcp/            Read-only MCP server for Claude Code
src/db/             SQLAlchemy models + Alembic migrations
scripts/            start.sh / stop.sh
tests/              Smoke tests (pytest)
specializations/    Hunting playbooks (IDOR/API, OAuth, AI/LLM)
core/               Methodology, ethics checklist, report template
```

See [CODE_ARCHITECTURE.md](CODE_ARCHITECTURE.md) for a full layer-by-layer breakdown.

---

## Specializations

| Phase | Focus | Status |
|---|---|---|
| Phase 1 | IDOR + API Security | Active |
| Phase 2 | OAuth + Authentication | After first paid finding |
| Phase 3 | AI/LLM Security | After Phase 2 |

---

## Ethics

This project is built for authorized bug bounty programs only. All testing is conducted within explicitly defined program scope. See [ETHICS.md](ETHICS.md) for full commitments.
