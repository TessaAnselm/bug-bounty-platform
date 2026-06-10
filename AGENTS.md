# Agent Working Notes

This project is a local-first ethical bug bounty research platform. Treat safety behavior as critical path, not as documentation-only policy.

## Priorities

1. Preserve scope enforcement. Out-of-scope targets must never be stored or acted on.
2. Preserve local-only dashboard assumptions unless explicitly changed.
3. Keep MCP read-only.
4. Add tests before or with changes to safety, auth, recon, reporting, and database behavior.
5. Prefer small, focused fixes over broad rewrites.

## QA Baseline

Before calling work complete, run:

```bash
.venv/bin/python -m pytest tests/ -q
```

For changes touching startup, also run:

```bash
bash scripts/start.sh
bash scripts/stop.sh
```

## High-Risk Areas

- `src/activities/storage/scope.py`
- `src/activities/storage/store_assets.py`
- `src/workflows/recon.py`
- `src/api/auth.py`
- `src/api/routers/programs.py`
- `src/activities/reporting/exporter.py`

## Documentation

Use `QA_TRACKER.md` to track QA coverage, gaps, and next checks.
