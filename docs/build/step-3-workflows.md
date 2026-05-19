# Step 3 — Temporal Workflows + Activities

## What We're Building

Four core Temporal workflows and all their activities. Build and verify in this order:
1. ProgramOnboardingWorkflow (simplest, good first test)
2. ReconWorkflow (most complex — build with mocks first)
3. FindingWorkflow (human-in-loop signals)
4. MonitorWorkflow (long-running scheduled loop)

## Prerequisites

- Steps 1 and 2 complete and verified
- All DB models working
- Recon tools installed: subfinder, httpx, katana, gau, gowitness, trufflehog

## Files to Create

```
src/
  workflows/
    __init__.py
    onboarding.py
    recon.py
    finding.py
    monitor.py
  activities/
    __init__.py
    recon/
      subdomain_enum.py      subfinder wrapper
      http_probe.py          httpx wrapper
      tech_fingerprint.py    technology detection
      screenshot.py          gowitness wrapper
      js_crawl.py            katana wrapper
      hist_urls.py           gau wrapper
      github_osint.py        trufflehog wrapper
    storage/
      store_assets.py        write assets to DB
      diff_assets.py         compare to previous run
    notifications/
      discord_alert.py       Discord webhook
    scoring/
      score_program.py       compute program score
  worker/
    main.py                  register all workflows + activities
```

## Build Order Within This Step

### 3a — ProgramOnboardingWorkflow

Simplest workflow. Validates scope, stores program, triggers recon.

```python
@workflow.defn
class ProgramOnboardingWorkflow:
    @workflow.run
    async def run(self, input: OnboardingInput) -> OnboardingResult:
        # 1. Validate scope (activity)
        # 2. Store program in DB (activity)
        # 3. Score program (activity)
        # 4. Spawn ReconWorkflow as child
        # 5. Spawn MonitorWorkflow as child
```

**Gate:** Create a program via CLI script → see it in DB → see child workflows start in Temporal UI.

### 3b — ReconWorkflow (mocked first)

Replace real tool calls with mock activities that return fixture data. Verify the full
flow works before adding real tools.

```python
@workflow.defn
class ReconWorkflow:
    @workflow.run
    async def run(self, input: ReconInput) -> ReconResult:
        # 1. enumerate_subdomains
        # 2. probe_hosts
        # 3. In parallel:
        #    - fingerprint_tech
        #    - capture_screenshots
        #    - crawl_js_files
        #    - collect_hist_urls
        # 4. github_osint
        # 5. store_assets
        # 6. diff_assets (compare to last run)
        # 7. send_alert if new assets found
```

**Gate (mocked):** Workflow completes → assets written to DB → diff shows correct new/unchanged counts.

**Gate (real tools):** Run against a test domain you own → verify each tool produces output.

### 3c — FindingWorkflow

Uses Temporal signals for human-in-loop status updates.

```python
@workflow.defn
class FindingWorkflow:
    _status: str = "draft"

    @workflow.signal
    async def update_status(self, new_status: str):
        self._status = new_status

    @workflow.run
    async def run(self, input: FindingInput) -> FindingResult:
        # 1. create_finding in DB
        # 2. generate_report_draft
        # 3. Wait for signals (submitted → triaged → accepted/rejected → paid)
        # 4. On each signal: update DB record
        # 5. On terminal state: record outcome
```

**Gate:** Create finding → send `update_status` signal via Temporal UI → verify DB record updates.

### 3d — MonitorWorkflow

Long-running. Uses `workflow.sleep` to schedule periodic recon.

```python
@workflow.defn
class MonitorWorkflow:
    _active: bool = True

    @workflow.signal
    async def stop(self):
        self._active = False

    @workflow.run
    async def run(self, input: MonitorInput):
        while self._active:
            await workflow.execute_child_workflow(
                ReconWorkflow,
                ReconInput(program_id=input.program_id)
            )
            await workflow.sleep(
                timedelta(hours=input.interval_hours)
            )
```

**Gate:** Workflow runs → sleeps → wakes → triggers recon → verify in Temporal UI history.

## Rate Limiting (Required in Recon Activities)

Every activity that makes external requests must respect limits:

```python
# In each recon activity:
RATE_LIMIT_RPS = int(os.getenv("RECON_RATE_LIMIT_RPS", "5"))
MAX_CONCURRENT = int(os.getenv("RECON_MAX_CONCURRENT", "2"))

# httpx activity example:
# httpx --rate-limit 5 --threads 2
```

## Ethics Gate Implementation

Before ReconWorkflow runs any external activities, check ethics checklist:

```python
async def check_ethics_gate(program_id: UUID) -> bool:
    # Query DB: has ethics checklist been completed for this program?
    # If not: block workflow, send Discord alert, raise ApplicationError
    pass
```

## Verification Gate (Full Step 3)

```bash
# 1. All 4 workflows registered in Temporal UI
#    Temporal UI → Workflows → should see all 4 workflow types

# 2. ProgramOnboarding creates program + spawns children
python src/scripts/onboard_program.py --name "test" --scope "example.com"

# 3. Recon runs and stores assets
#    Check DB: SELECT count(*) FROM assets WHERE program_id = '<id>';

# 4. Finding workflow accepts signals
python src/scripts/create_finding.py --program-id <id> --title "test finding"
#    Then send signal via Temporal UI or:
python src/scripts/update_finding.py --finding-id <id> --status submitted

# 5. Monitor workflow appears long-running in Temporal UI
#    Should show status "Running", not "Completed"
```
