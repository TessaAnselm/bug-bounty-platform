# Commands Cheat-Sheet

Quick reference for running the Bug Bounty Platform. Copy-paste from here.

**Conventions**
- Run all commands from the project root (no `cd` needed).
- Python commands use the project venv: `.venv/bin/python`.
- URLs: Dashboard → http://localhost:8000 · Temporal UI → http://localhost:8080

---

## 1. Start / stop the platform

```bash
./scripts/start.sh
```
Starts Docker containers (if down), the Temporal worker, and the FastAPI dashboard. Prints the dashboard URL when done.

```bash
./scripts/start.sh myNewKey
```
Same, but rotates the dashboard API key to `myNewKey` (only the SHA-256 hash is stored).

```bash
./scripts/stop.sh
```
Stops the worker and dashboard (Docker containers keep running).

> **Gotcha:** the worker and dashboard read `.env` **and** the Python code at **startup**. After editing `.env` or any `src/` code, you must `./scripts/stop.sh && ./scripts/start.sh` for changes to take effect.

---

## 2. Docker (database + Temporal)

```bash
docker compose up -d
```
Start PostgreSQL + Temporal + Temporal UI in the background (survives terminal close).

```bash
docker compose ps
```
Show container status — look for `healthy` on postgresql.

```bash
docker compose logs --tail 60 temporal
```
View Temporal server logs (use `postgresql` or `temporal-ui` for the others).

```bash
docker compose down
```
Stop and remove containers (data persists in the volume).

---

## 3. Database migrations

```bash
.venv/bin/alembic current
```
Show which migration the DB is on. `xxxx (head)` means it's fully up to date.

```bash
.venv/bin/alembic upgrade head
```
Apply any pending migrations (build/upgrade all tables). Safe to re-run.

---

## 4. Onboard a program

**Easiest:** Dashboard → **Discover** → click **"Onboard →"** next to a program. Auto-imports scope + out-of-scope from bounty-targets-data and writes it to the DB.

**Script (also triggers recon via the onboarding workflow):**
```bash
.venv/bin/python -m src.scripts.onboard_program \
  --name "Example" --platform hackerone \
  --scope "api.example.com" "app.example.com" \
  --out-of-scope "blog.example.com" \
  --max-payout 10000
```
Onboards a program with an explicit scope. Use **specific hostnames, not wildcards**, for small/fast recon.

---

## 5. Run recon

```bash
.venv/bin/python scripts/trigger_recon.py --list
```
List onboarded programs (name, status, ID).

```bash
.venv/bin/python scripts/trigger_recon.py --program "<PROGRAM NAME>"
```
Submit a ReconWorkflow for an onboarded program. The worker executes it:
subfinder → httpx probe → store → diff → alert.

```bash
.venv/bin/python scripts/trigger_recon.py --program "<PROGRAM NAME>" --dry-run
```
Preview what would run without submitting.

---

## 6. Check status / view results

**No-CLI (preferred):** Dashboard → **Health** (recon run status) and **Assets** (discovered hosts); Temporal UI for activity-by-activity detail (click `enumerate_subdomains` → *Input and Results* to see the discovered list).

**Latest recon run, from the terminal:**
```bash
.venv/bin/python -c "from src.db.session import engine; from src.db.models import ReconRun; from sqlalchemy.orm import Session; from sqlalchemy import select; s=Session(engine); r=s.execute(select(ReconRun).order_by(ReconRun.started_at.desc())).scalars().first(); print('status:', r.status, '| assets_found:', r.assets_found, '| new:', r.new_assets, '| started:', r.started_at)"
```
Prints the most recent run's status (`running` → `completed`/`failed`) and asset counts.

**A program's scope/constraints, from the terminal:**
```bash
.venv/bin/python -c "from src.db.session import engine; from src.db.models import Program; from sqlalchemy.orm import Session; from sqlalchemy import select; s=Session(engine); p=s.execute(select(Program).where(Program.name=='<PROGRAM NAME>')).scalar_one(); print('platform:', p.platform, '| scope:', len(p.scope or []), '| oos:', len(p.out_of_scope or []), '| constraints:', p.constraints)"
```

---

## 7. Logs

```bash
tail -f logs/worker.log
```
Follow the worker (recon activity output appears here).

```bash
grep -E "scope filter|subfinder|httpx|probe_hosts|gau|katana" logs/worker.log | tail -20
```
Show only recon activity lines (skips Temporal connection noise).

```bash
: > logs/worker.log
```
Truncate the worker log (safe during a run — clears stale errors so `tail -f` is readable).

```bash
tail -f logs/dashboard.log
```
Follow the dashboard (HTTP requests, startup).

> **Gotcha:** `worker.log` is append-only and the Temporal client only logs **errors**. A healthy worker writes nothing, so the visible tail can show *old* `Connection refused` lines from a previous run. Check the **timestamps** — if they're not current, they're stale and harmless.

---

## 8. Recon compliance (per-program)

- **Rate limit:** global default is **3 req/sec** (`RECON_RATE_LIMIT_RPS` in `.env`). Raise it for a single permissive program via Dashboard → program → **Program Constraints → Rate limit (req/min)**.
- **HackerOne header:** set `HACKERONE_RESEARCH_USERNAME` in `.env`; the probe auto-adds `X-HackerOne-Research: <username>` for hackerone-platform programs.
- **Active scanning** (katana/gowitness) is **off by default** (passive-only). Enable per program via **Program Constraints → Allow active scanning**.

---

## 9. Security / quality checks

```bash
snyk code test
```
Static analysis (SAST) of the codebase. `Total issues: 0` is clean. Run `snyk auth` first if you get `403 Forbidden`.

```bash
gitleaks detect --source . --no-banner
```
Scan for committed secrets (install with `brew install gitleaks`).

```bash
.venv/bin/python -m pytest -q
```
Run the test suite.

---

## 10. Git (you run these yourself)

```bash
git status
git add <file>
git commit -m "subject" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
`.env` is gitignored and must never be committed.

---

## Other scripts (run with `--help` for exact flags)

```bash
.venv/bin/python scripts/import_recon.py --help     # import recon results
.venv/bin/python scripts/fetch_osint.py --help      # pull OSINT data
.venv/bin/python scripts/select_program.py --help   # program scoring/selection
.venv/bin/python -m src.scripts.create_finding --help   # create a finding
.venv/bin/python -m src.scripts.update_finding --help   # update a finding's status
```
