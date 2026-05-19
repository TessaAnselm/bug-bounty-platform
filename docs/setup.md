# Setup Guide

> **Note:** The files referenced below (`docker-compose.yml`, `requirements.txt`, `src/`, `alembic/`) are created during the build steps in `docs/build/`. Complete Steps 1–3 before running this guide.

Get the platform running from scratch on a new machine.

## Prerequisites

Install these before running the setup script:

```bash
# Docker Desktop
# https://www.docker.com/products/docker-desktop/

# Python 3.12
brew install python@3.12

# GitHub CLI (for repo management)
brew install gh

# Recon tools
brew install go
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest
go install github.com/lc/gau/v2/cmd/gau@latest
go install github.com/sensepost/gowitness@latest
go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
pip install trufflehog

# Python dependencies
pip install -r requirements.txt
```

## First-Time Setup

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/bug-bounty-platform.git
cd bug-bounty-platform

# 2. Create environment file
cp .env.example .env
# Edit .env — change all "changeme" values

# 3. Start infrastructure
docker compose up -d

# 4. Wait for Temporal to be ready (~30 seconds)
docker compose logs temporal | grep "started serving"

# 5. Run database migrations
alembic upgrade head

# 6. Verify everything is running
python src/scripts/healthcheck.py
```

## Verify Setup

```
Temporal UI:    http://localhost:8080   should show "default" namespace
Dashboard:      http://localhost:8000   requires DASHBOARD_API_KEY header
PostgreSQL:     localhost:5432          check with psql or TablePlus
```

## Stopping and Starting

```bash
# Stop all services (keeps data)
docker compose stop

# Start again
docker compose start

# Full reset (destroys all data — use with caution)
docker compose down -v
```

## Daily Usage

```bash
# Start platform
docker compose start

# Start worker (if not running in Docker)
python -m src.worker.main

# Start dashboard (if not running in Docker)
uvicorn src.api.main:app --reload
```
