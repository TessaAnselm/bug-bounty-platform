#!/usr/bin/env bash
# Exit immediately if any command fails — prevents silent partial starts
# where Docker is up but the worker crashed and we never noticed.
set -euo pipefail

# Resolve the project root from wherever this script lives,
# so it works regardless of which directory you run it from.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$PROJECT_DIR/logs"
VENV="$PROJECT_DIR/.venv/bin"

cd "$PROJECT_DIR"

echo "==> Bug Bounty Platform — Starting up"
echo ""

# ── Preflight checks ───────────────────────────────────────────────────────

# Create the logs directory if it doesn't exist yet.
# Without this, background process redirection (>> logs/worker.log) would fail.
mkdir -p "$LOGS"

# Ensure .env exists so grep/perl don't error on a missing file.
touch "$PROJECT_DIR/.env"

# Verify the virtualenv was set up before trying to use it.
# If python or uvicorn aren't there, everything below would fail with
# confusing "command not found" errors instead of a clear message.
if [ ! -x "$VENV/python" ] || [ ! -x "$VENV/uvicorn" ]; then
  echo "ERROR: Virtualenv not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Check Docker Compose is available as a plugin (modern v2 syntax).
# Older installs use a separate `docker-compose` binary — this catches that mismatch early.
if ! docker compose version &>/dev/null; then
  echo "ERROR: Docker Compose is not available."
  exit 1
fi

# ── API key ────────────────────────────────────────────────────────────────
# Usage: ./start.sh              → keeps existing key, or generates one on first run
#        ./start.sh mypassword   → sets "mypassword" as the key (run once to establish it)
#
# Only the SHA-256 hash is stored in .env — plaintext is never saved to disk.
# Once a key is set, restarts reuse the existing hash so browser cookies stay
# valid across restarts. To rotate the key, pass a new argument explicitly.
#
# API_KEY is intentionally kept as a shell variable only, not exported.
# It is only populated when we generate/set a new key so we can print the URL.

EXISTING_HASH=$(grep "^DASHBOARD_API_KEY=" "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2)

if [ -n "${1:-}" ]; then
  # Explicit argument — rotate to a new known key
  API_KEY="$1"
  echo "  Key: using provided argument"
  KEY_HASH=$(RAW_KEY="$API_KEY" "$VENV/python" -c \
    "import hashlib, os; print(hashlib.sha256(os.environ['RAW_KEY'].encode()).hexdigest())")
  if grep -q "^DASHBOARD_API_KEY=" "$PROJECT_DIR/.env" 2>/dev/null; then
    perl -0pi -e "s/^DASHBOARD_API_KEY=.*/DASHBOARD_API_KEY=$KEY_HASH/m" "$PROJECT_DIR/.env"
  else
    echo "DASHBOARD_API_KEY=$KEY_HASH" >> "$PROJECT_DIR/.env"
  fi
elif [ -n "$EXISTING_HASH" ]; then
  # Key already set — reuse it so existing browser cookies stay valid
  API_KEY=""
  echo "  Key: using existing key from .env (browser session preserved)"
else
  # First run — generate a random key and store its hash
  API_KEY=$("$VENV/python" -c "import secrets; print(secrets.token_urlsafe(32))")
  echo "  Key: generated new key (first run)"
  KEY_HASH=$(RAW_KEY="$API_KEY" "$VENV/python" -c \
    "import hashlib, os; print(hashlib.sha256(os.environ['RAW_KEY'].encode()).hexdigest())")
  echo "DASHBOARD_API_KEY=$KEY_HASH" >> "$PROJECT_DIR/.env"
fi

# ── 1. Docker containers ───────────────────────────────────────────────────
echo "[1/3] Docker containers..."

# Docker Desktop must be running before we can talk to the daemon.
# `docker info` is the standard liveness check — exits non-zero if daemon is down.
if ! docker info &>/dev/null; then
  echo "     ERROR: Docker is not running. Start Docker Desktop first."
  exit 1
fi

# Count running containers. We expect at least 3: PostgreSQL, Temporal server, Temporal UI.
# If all 3 are already up, skip the compose start to avoid disrupting running workflows.
RUNNING=$(docker compose ps --status running --quiet 2>/dev/null | wc -l | tr -d ' ')
if [ "$RUNNING" -ge 3 ]; then
  echo "     Already running ✓"
else
  docker compose up -d
  # pg_isready is more reliable than a fixed sleep — it polls until PostgreSQL
  # accepts connections, which is what Temporal and the app actually need.
  echo "     Waiting for PostgreSQL to be healthy..."
  until docker compose exec -T postgresql pg_isready -U bounty &>/dev/null; do
    sleep 1
  done
  echo "     Containers healthy ✓"
fi

# ── 2. Temporal worker ─────────────────────────────────────────────────────
echo "[2/3] Temporal worker..."

# Check the PID file instead of pgrep -f to avoid matching unrelated processes
# on the same machine that happen to share the module name "src.worker.main".
# kill -0 sends no signal — it just checks if the PID is alive.
if [ -f "$LOGS/worker.pid" ] && kill -0 "$(cat "$LOGS/worker.pid")" 2>/dev/null; then
  echo "     Already running ✓"
else
  # Remove stale PID file before starting so we never read a leftover value.
  rm -f "$LOGS/worker.pid"
  "$VENV/python" -m src.worker.main >> "$LOGS/worker.log" 2>&1 &
  echo $! > "$LOGS/worker.pid"
  # TODO: Replace sleep with a proper readiness check (e.g. poll Temporal gRPC
  #       until the worker registers) so slow machines don't produce false failures.
  sleep 2
  if kill -0 "$(cat "$LOGS/worker.pid")" 2>/dev/null; then
    echo "     Started (PID $(cat "$LOGS/worker.pid")) ✓"
  else
    echo "     ERROR: Worker failed to start. Check logs/worker.log"
    exit 1
  fi
fi

# ── 3. FastAPI dashboard ───────────────────────────────────────────────────
echo "[3/3] FastAPI dashboard..."

# Same PID-file check as the worker — avoids broad pgrep matches.
if [ -f "$LOGS/dashboard.pid" ] && kill -0 "$(cat "$LOGS/dashboard.pid")" 2>/dev/null; then
  echo "     Already running ✓"
  # FastAPI loads .env once at startup, so a running dashboard still holds
  # the old key in memory even though .env was just updated above.
  echo "     NOTE: Restart required if you changed the API key (stop.sh then start.sh)"
else
  # Remove stale PID file before starting so we never read a leftover value.
  rm -f "$LOGS/dashboard.pid"
  # Bind to 127.0.0.1 (loopback only) — NOT 0.0.0.0.
  # 0.0.0.0 would expose the dashboard to everyone on the same WiFi network.
  # This is a personal research tool; it should only be reachable from this machine.
  "$VENV/uvicorn" src.api.main:app --host 127.0.0.1 --port 8000 >> "$LOGS/dashboard.log" 2>&1 &
  echo $! > "$LOGS/dashboard.pid"
  # TODO: Same as worker — replace sleep with a real health check
  #       (curl localhost:8000/health/live) once the endpoint is confirmed stable.
  sleep 2
  if kill -0 "$(cat "$LOGS/dashboard.pid")" 2>/dev/null; then
    echo "     Started (PID $(cat "$LOGS/dashboard.pid")) ✓"
  else
    echo "     ERROR: Dashboard failed to start. Check logs/dashboard.log"
    exit 1
  fi
fi

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo "==> All systems up"
echo ""
if [ -n "$API_KEY" ]; then
  echo "  Dashboard   http://localhost:8000?api_key=$API_KEY"
  echo "              (login once — cookie lasts 7 days)"
else
  echo "  Dashboard   http://localhost:8000"
fi
echo "  Temporal UI http://localhost:8080"
echo "  Logs        $LOGS/"
echo ""
echo "  Stop with: ./scripts/stop.sh"
