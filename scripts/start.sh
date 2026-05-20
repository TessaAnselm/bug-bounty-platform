#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$PROJECT_DIR/logs"
VENV="$PROJECT_DIR/.venv/bin"

cd "$PROJECT_DIR"

echo "==> Bug Bounty Platform — Starting up"
echo ""

# ── 1. Docker containers ───────────────────────────────────────────────────
echo "[1/3] Docker containers..."
if ! docker info &>/dev/null; then
  echo "     ERROR: Docker is not running. Start Docker Desktop first."
  exit 1
fi

RUNNING=$(docker compose ps --status running --quiet 2>/dev/null | wc -l | tr -d ' ')
if [ "$RUNNING" -ge 3 ]; then
  echo "     Already running ✓"
else
  docker compose up -d
  echo "     Waiting for PostgreSQL to be healthy..."
  until docker compose exec -T postgresql pg_isready -U bounty &>/dev/null; do
    sleep 1
  done
  echo "     Containers healthy ✓"
fi

# ── 2. Temporal worker ─────────────────────────────────────────────────────
echo "[2/3] Temporal worker..."
if pgrep -f "src.worker.main" &>/dev/null; then
  echo "     Already running ✓"
else
  "$VENV/python" -m src.worker.main >> "$LOGS/worker.log" 2>&1 &
  echo $! > "$LOGS/worker.pid"
  sleep 2
  if pgrep -f "src.worker.main" &>/dev/null; then
    echo "     Started (PID $(cat "$LOGS/worker.pid")) ✓"
  else
    echo "     ERROR: Worker failed to start. Check logs/worker.log"
    exit 1
  fi
fi

# ── 3. FastAPI dashboard ───────────────────────────────────────────────────
echo "[3/3] FastAPI dashboard..."
if pgrep -f "src.api.main:app" &>/dev/null; then
  echo "     Already running ✓"
else
  "$VENV/uvicorn" src.api.main:app --host 0.0.0.0 --port 8000 >> "$LOGS/dashboard.log" 2>&1 &
  echo $! > "$LOGS/dashboard.pid"
  sleep 2
  if pgrep -f "src.api.main:app" &>/dev/null; then
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

API_KEY=$(grep DASHBOARD_API_KEY "$PROJECT_DIR/.env" 2>/dev/null | cut -d= -f2 | tr -d '"' || echo "changeme")

echo "  Dashboard   http://localhost:8000?api_key=$API_KEY"
echo "  Temporal UI http://localhost:8080"
echo "  Logs        $LOGS/"
echo ""
echo "  Stop with: ./scripts/stop.sh"
