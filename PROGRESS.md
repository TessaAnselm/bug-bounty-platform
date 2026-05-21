# Build Progress

Track current state here. Update this file as each step completes.

---

## Current Status

**Phase:** V1 Complete — Safety Hardened — Ready to Hunt
**Current Step:** First Program Onboarding
**Last Session:** Safety guardrails added post-V1: scope enforcement, confidence scoring, SECURITY.md, ETHICS.md, SCOPE_POLICY.md. README and CODE_ARCHITECTURE.md updated.

---

## V1 Build Steps

- [x] **Step 1** — Docker Compose + Temporal + PostgreSQL
  - Docker Compose file with: Temporal server, Temporal UI, PostgreSQL
  - Temporal UI accessible at localhost:8080 ✓
  - PostgreSQL healthy ✓
  - `.env.example` with all required variables ✓

- [x] **Step 2** — Database schema + Alembic migrations
  - All 9 tables from data model ✓
  - Alembic configured and initial migration generated ✓
  - Migration runs clean, downgrade/upgrade round-trip verified ✓
  - Snyk code scan: 0 issues ✓

- [x] **Step 3** — Python Temporal workers + 4 core workflows
  - ProgramOnboardingWorkflow ✓
  - ReconWorkflow (subfinder → httpx → katana → gau → gowitness → store → diff → alert) ✓
  - MonitorWorkflow (long-running scheduled loop) ✓
  - FindingWorkflow (human-in-loop signals) ✓
  - Rate limiting enforced in recon activities ✓
  - Ethics checklist gate before recon starts ✓

- [x] **Step 4** — FastAPI dashboard
  - Program list view with scoring ✓
  - Asset view per program (highlight new assets) ✓
  - Finding pipeline (kanban by status) ✓
  - Alerts panel ✓
  - Session notes per asset ✓
  - Workflow health view (links to Temporal UI) ✓
  - Basic API key auth ✓
  - Snyk: fixed 2 open redirect vulns, 0 issues ✓

- [x] **Step 5** — MCP server
  - Local Python MCP server ✓
  - Read-only resources: programs, assets, findings, alerts, session_notes,
    recon_runs, program_scores ✓
  - 2 tools: search_assets, summarize_program ✓
  - Registered in .mcp.json (Claude Code auto-discovers on restart) ✓
  - Snyk code scan: 0 issues ✓

- [x] **Step 6** — CI pipeline
  - GitHub Actions workflow ✓
  - gitleaks on every push (secrets check) ✓
  - Snyk code scan on every push ✓
  - Semgrep on every push ✓
  - pytest on every push (6 smoke tests) ✓

- [x] **Post-V1 Safety Hardening**
  - SECURITY.md — safety architecture and responsible disclosure ✓
  - ETHICS.md — ethics commitments and pre-engagement checklist ✓
  - SCOPE_POLICY.md — scope definition and enforcement docs ✓
  - validate_target() — technical scope enforcement in store_assets ✓
  - confidence_score — 0.00–1.00 field on findings (DB migrated) ✓
  - README.md and CODE_ARCHITECTURE.md updated ✓

---

## V2 Build Steps (After First Paid Finding)

- [ ] Program discovery (bounty-targets-data integration)
- [ ] Full program scoring model
- [ ] HackerOne / Bugcrowd API sync
- [ ] CT log monitoring (crt.sh)
- [ ] Outcomes / feedback loop
- [ ] Report export pipeline
- [ ] Artifact storage (structured)

---

## Decisions Made

| Decision | Choice | Reason |
|---|---|---|
| Workflow engine | Temporal OSS | Durability, observability, human-in-loop signals |
| Database | PostgreSQL | Temporal needs it anyway, avoid SQLite + PG split |
| AI integration | MCP read-only | Free (Claude Code subscription), no API cost |
| AI models | Claude Code only | No ChatGPT — breaks free requirement |
| Dashboard | FastAPI + Jinja2 | Lightweight, no JS framework needed for v1 |
| Notifications | Discord webhook | Free, instant, zero infrastructure |
| Scoring | 5-dimension weighted | Payout, Scope, Competition, Fit, Momentum |
| Recon tools | ProjectDiscovery suite | Free, maintained, composable |
| First target | Anthropic HackerOne | New program, low competition, AI/LLM edge |
| Platform security | Snyk + Semgrep + gitleaks | All free, complementary coverage |
| Temporal workflows | 4 core only (v1) | Avoid over-engineering before first use |

