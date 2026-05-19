# Step 1 — Infrastructure: Docker Compose + Temporal + PostgreSQL

## What We're Building

The foundation everything else runs on:
- PostgreSQL (single database for both Temporal and the app)
- Temporal server + UI (workflow orchestration)
- Python worker container (runs workflow activities)

## Prerequisites

- Docker Desktop installed and running
- `.env` file created from `.env.example` with values filled in

## Files to Create

```
docker-compose.yml
src/
  worker/
    __init__.py
    main.py          worker entry point
```

## docker-compose.yml Structure

Five services:

```
postgresql          database (Temporal + app share this)
temporal            Temporal server
temporal-ui         Temporal web UI (localhost:8080)
temporal-admin      one-shot setup container
app                 FastAPI dashboard
worker              Temporal Python worker
```

## Verification Gate

All of the following must pass before moving to Step 2:

```bash
# 1. All containers running
docker compose ps
# Expected: all services "Up", no "Exit" or "Restarting"

# 2. Temporal UI accessible
open http://localhost:8080
# Expected: Temporal Web UI loads, shows "default" namespace

# 3. PostgreSQL accepting connections
docker compose exec postgresql psql -U bounty -d bountydb -c "\dt"
# Expected: connects successfully (no tables yet — that's Step 2)

# 4. Worker registered in Temporal
# In Temporal UI → Workers → should show at least one worker connected

# 5. Simple workflow executes
# Run: python src/scripts/healthcheck.py
# Expected: "Workflow completed successfully"
```

## Common Issues

**Temporal fails to start:**
- PostgreSQL must be healthy before Temporal starts — check `depends_on` with healthcheck
- Default Temporal ports: 7233 (gRPC), 8080 (UI) — check for conflicts

**Worker can't connect to Temporal:**
- Verify `TEMPORAL_HOST` in `.env` matches the service name in docker-compose
- Inside Docker network, use service name (`temporal`), not `localhost`

**PostgreSQL connection refused:**
- Check `POSTGRES_PASSWORD` matches in both `.env` and docker-compose
- Volume may have stale data — `docker compose down -v` and restart

## Notes

- Temporal requires its own internal schema — the `temporal-admin` container runs
  `temporal-sql-tool` to set this up automatically on first run
- The app and Temporal share PostgreSQL but use different databases/schemas
- Worker container uses a `watchfiles` reload in development so code changes
  apply without restart
