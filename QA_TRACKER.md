# QA Checklist

This checklist tracks whether BountyOS is safe, reliable, and ready to use on authorized programs. Prefer automated tests for every item that can be tested without touching real targets.

## Baseline

- Test command: `.venv/bin/python -m pytest tests/ -q`
- Current automated result: `25 passed`
- Rule: tests must not hit real bug bounty targets.
- Rule: database tests must use a test database, not the live bounty database.
- Rule: workflow tests should mock recon activities unless explicitly testing the local stack.

## Safety Gates

- [x] Empty scope rejects all targets.
- [x] Out-of-scope entries override in-scope entries.
- [x] Wildcard scope allows matching subdomains.
- [x] URL targets are normalized before scope matching.
- [ ] Scope matching handles ports predictably.
- [ ] Scope matching handles uppercase/mixed-case targets.
- [x] Store-assets rejects out-of-scope probe results before DB write.
- [x] Store-assets rejects all probe results when program scope is empty.
- [x] Program status blocks recon unless status is `active`.
- [ ] Active recon tools run only when `allow_active_scanning` is enabled.

## Authentication

- [x] Valid raw API key is accepted.
- [x] Invalid raw API key is rejected.
- [x] Session token round trip works.
- [x] Tampered session token is rejected.
- [x] Expired session token is rejected.
- [x] Empty `DASHBOARD_API_KEY` fails closed.
- [ ] Browser login sets a session cookie, not the raw API key.
- [ ] Login rejects invalid key without setting a session cookie.
- [ ] Logout clears the session cookie.
- [ ] Protected dashboard routes redirect unauthenticated users to login.

## Reporting

- [x] Markdown export includes title, program, asset, severity, and confidence.
- [x] HackerOne export renders missing fields safely.
- [x] Markdown export renders missing fields safely.
- [x] Bugcrowd export maps critical severity to `P1`.
- [ ] HackerOne export includes all expected submission sections.
- [ ] Bugcrowd export includes all expected submission sections.
- [ ] Finding detail export route returns downloadable content.

## Scoring And Triage

- [x] High-value API assets receive higher risk scores.
- [x] Risk score is capped at 100.
- [x] Auto-tagging combines asset value and technology signals.
- [ ] Low-signal assets receive low scores.
- [ ] Triage route sorts by risk score.
- [ ] Interesting toggle persists correctly.

## Database

- [ ] Migrations upgrade cleanly from an empty database.
- [ ] Migrations downgrade/upgrade round trip cleanly.
- [ ] Program can be created with scope and out-of-scope lists.
- [ ] Duplicate programs are handled predictably.
- [x] Duplicate assets are not created for the same program/type/value.
- [x] Existing asset updates refresh status, tech, tags, risk, and source.
- [ ] Findings can be created, updated, and associated with assets.
- [ ] Outcomes can be recorded and payout mirrors to finding when paid.

## Dashboard Routes

- [ ] Program list loads for authenticated user.
- [ ] Program detail loads for authenticated user.
- [ ] Program scope update saves valid entries.
- [ ] Program scope update warns on skipped entries.
- [ ] Program status transitions follow allowed state changes.
- [ ] Program discover page handles upstream fetch failure cleanly.
- [ ] Asset detail loads notes and findings.
- [ ] Finding create/update flow works.
- [ ] Hunt session can start from an asset.
- [ ] Checklist progress persists.
- [ ] Alerts can be marked seen.

## Workflows

- [ ] Recon workflow creates a recon run.
- [ ] Recon workflow marks successful run completed.
- [ ] Recon workflow marks failed run failed.
- [ ] Recon workflow passes scope and out-of-scope to storage.
- [ ] Recon workflow skips active tools by default.
- [ ] Recon workflow honors per-program rate limit constraints.
- [ ] Monitor workflow starts recon on schedule.
- [ ] Finding workflow requires human status signals.

## External Tool Handling

- [ ] Missing `subfinder` does not crash worker.
- [ ] Missing `httpx` does not crash worker.
- [ ] Recon timeout is handled and reported.
- [ ] GitHub OSINT skips cleanly when token is absent.
- [ ] Optional OSINT API keys skip cleanly when absent.
- [ ] Tool failures are visible in logs or dashboard health.

## Startup And Operations

- [ ] `scripts/start.sh` verifies Docker is running.
- [ ] `scripts/start.sh` verifies PostgreSQL readiness.
- [ ] `scripts/start.sh` verifies dashboard readiness via `/health/live`.
- [ ] `scripts/start.sh` verifies worker readiness without fixed sleeps.
- [ ] `scripts/stop.sh` stops dashboard and worker without touching Docker data.
- [ ] Restart preserves existing dashboard key unless explicitly rotated.
- [ ] Dashboard remains bound to `127.0.0.1`.

## MCP

- [ ] MCP server lists expected resources.
- [ ] MCP resource reads are read-only.
- [ ] MCP search handles empty query safely.
- [ ] MCP summarize handles missing program safely.
- [ ] MCP tools do not mutate database state.

## Manual Pre-Hunt QA

Run this before using the platform on a real authorized program:

- [ ] Create a fake program with safe test scope.
- [ ] Add in-scope and out-of-scope entries.
- [ ] Import sample recon data.
- [ ] Confirm out-of-scope assets are rejected.
- [ ] Confirm no real target traffic is generated.
- [ ] Start a hunt session.
- [ ] Create a draft finding.
- [ ] Export markdown, HackerOne, and Bugcrowd report drafts.
- [ ] Pause the program.
- [ ] Confirm recon refuses to run while paused.
- [ ] Archive the program.
- [ ] Confirm archived programs are hidden by default.

## Release Blockers

Any of these should block use on a real program until fixed:

- Scope bypass or out-of-scope storage.
- Raw API key stored in browser cookie, URLs, logs, or templates.
- Recon can run on paused or archived programs.
- Active scanning runs without explicit program permission.
- Failed recon appears successful.
- Tests require real external targets.
- Test data writes to the live bounty database.
