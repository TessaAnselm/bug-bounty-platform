# Step 4 — FastAPI Dashboard

## What We're Building

A local web dashboard for your hunting view: programs, assets, findings pipeline, alerts, and workflow health.

## Prerequisites

- Steps 1–3 complete and verified
- Real data in the DB from at least one test program

## Files to Create

```
src/
  api/
    __init__.py
    main.py              FastAPI app, auth middleware
    routers/
      programs.py        program CRUD + scoring view
      assets.py          asset list, filter, detail
      findings.py        finding pipeline, status update
      alerts.py          unseen alerts, mark seen
      notes.py           session notes CRUD
      health.py          workflow health, recon run history
    templates/
      base.html          layout, nav, auth check
      programs/
        index.html       program list with scores
        detail.html      program detail, asset list
      assets/
        index.html       asset list with filters
        detail.html      asset detail, notes, findings
      findings/
        pipeline.html    kanban by status
        detail.html      finding detail, report draft
      alerts/
        index.html       alert feed
      health/
        index.html       workflow health, recon history
    static/
      style.css
```

## Authentication

Simple API key middleware — no user accounts needed:

```python
API_KEY = os.getenv("DASHBOARD_API_KEY")

async def verify_api_key(request: Request):
    # Check X-API-Key header or ?api_key= query param
    # Raise 401 if missing or wrong
    # Apply to all routes except /health (liveness check)
```

## Key Views

### Program List (`/programs`)
- Cards ranked by program score
- Score breakdown on hover (payout / scope / competition / fit / momentum)
- Status badge (active / paused / archived)
- Latest recon run timestamp + new asset count
- Unseen alert count badge

### Asset View (`/programs/{id}/assets`)
- Table: value, type, status, technologies, first seen, last seen
- Highlight `is_new = true` rows
- Filter by: type, status, is_new, technology
- Click → asset detail with notes and linked findings

### Finding Pipeline (`/findings`)
- Kanban columns: Draft → Submitted → Triaged → Accepted → Paid / Rejected
- Click card → finding detail with report draft
- Status update button → sends Temporal signal

### Alerts (`/alerts`)
- Feed of unseen alerts (new asset, asset changed, workflow failed)
- Mark seen individually or all at once

### Health (`/health`)
- Recon runs last 7 days: status, assets found, new assets, duration
- Link to Temporal UI for full workflow history

## Verification Gate

```bash
# 1. Dashboard starts
uvicorn src.api.main:app --reload
open http://localhost:8000

# 2. Auth works
curl http://localhost:8000/programs
# Expected: 401 Unauthorized

curl -H "X-API-Key: yourkey" http://localhost:8000/programs
# Expected: program list renders

# 3. All views load with real data
# - Program list shows at least one program with score
# - Asset view shows assets from test recon run
# - Finding pipeline loads (may be empty)
# - Alerts feed loads
# - Health view shows recon run history

# 4. Finding status update works
# - Create a test finding
# - Click status update in dashboard
# - Verify Temporal receives signal
# - Verify DB record updates
```

## Notes

- Use Jinja2 templates — no JavaScript framework needed for v1
- Keep CSS minimal — readable tables and cards, no design complexity
- Temporal UI runs separately on port 8080 — link to it from Health view
  rather than trying to embed it
