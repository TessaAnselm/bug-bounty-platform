#!/usr/bin/env bash

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$PROJECT_DIR/logs"

cd "$PROJECT_DIR"

echo "==> Bug Bounty Platform — Shutting down"
echo ""

# ── Worker ─────────────────────────────────────────────────────────────────
echo "[1/2] Stopping Temporal worker..."
if [ -f "$LOGS/worker.pid" ]; then
  PID=$(cat "$LOGS/worker.pid")
  kill "$PID" 2>/dev/null && echo "     Stopped (PID $PID) ✓" || echo "     Already stopped"
  rm -f "$LOGS/worker.pid"
else
  pkill -f "src.worker.main" 2>/dev/null && echo "     Stopped ✓" || echo "     Not running"
fi

# ── Dashboard ──────────────────────────────────────────────────────────────
echo "[2/2] Stopping FastAPI dashboard..."
if [ -f "$LOGS/dashboard.pid" ]; then
  PID=$(cat "$LOGS/dashboard.pid")
  kill "$PID" 2>/dev/null && echo "     Stopped (PID $PID) ✓" || echo "     Already stopped"
  rm -f "$LOGS/dashboard.pid"
else
  pkill -f "src.api.main:app" 2>/dev/null && echo "     Stopped ✓" || echo "     Not running"
fi

echo ""
echo "==> Docker containers left running (PostgreSQL + Temporal)"
echo "    To stop Docker too: docker compose down"
echo ""
