# Step 2 — Database Schema + Alembic Migrations

## What We're Building

The full application schema in PostgreSQL, managed by Alembic for version-controlled migrations.

## Prerequisites

- Step 1 complete and verified
- PostgreSQL running and accessible
- Python environment set up with dependencies installed

## Files to Create

```
src/
  db/
    __init__.py
    base.py          SQLAlchemy declarative base
    session.py       database session factory
    models/
      __init__.py
      program.py
      asset.py
      finding.py
      recon_run.py
      alert.py
      session_note.py
      outcome.py
      program_score.py
      artifact.py
  alembic/
    env.py
    versions/        auto-generated migration files
alembic.ini
```

## Tables to Create

In dependency order:

```
1. programs
2. assets            (FK → programs)
3. findings          (FK → programs, assets)
4. recon_runs        (FK → programs)
5. alerts            (FK → programs, assets)
6. session_notes     (FK → programs, assets)
7. outcomes          (FK → findings)
8. program_scores    (FK → programs)
9. artifacts         (FK → findings, assets)
```

Full schema defined in `CLAUDE.md` → Data Model section.

## Key SQLAlchemy Conventions

```python
# All primary keys: UUID generated server-side
id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

# All timestamps: timezone-aware
created_at = Column(DateTime(timezone=True), server_default=func.now())

# JSONB for flexible fields (scope, technologies, ports, top_signals)
scope = Column(JSONB, nullable=False, default=list)

# Enums: define in Python, use in columns
class ProgramStatus(enum.Enum):
    active = "active"
    paused = "paused"
    archived = "archived"
```

## Verification Gate

```bash
# 1. Generate and run initial migration
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
# Expected: no errors, "Done" message

# 2. Verify all tables exist
docker compose exec postgresql psql -U bounty -d bountydb -c "\dt"
# Expected: 9 tables listed

# 3. Verify schema is correct (spot check)
docker compose exec postgresql psql -U bounty -d bountydb \
  -c "\d findings"
# Expected: columns match the data model

# 4. Verify Alembic tracks version
alembic current
# Expected: shows current revision hash

# 5. Verify downgrade works
alembic downgrade -1
alembic upgrade head
# Expected: both run cleanly
```

## Common Issues

**autogenerate misses columns:**
- Ensure all models are imported in `alembic/env.py` before `target_metadata`
- Check `Base.metadata` includes all models

**JSONB type not found:**
- Use `sqlalchemy.dialects.postgresql.JSONB` not generic `JSON`

**UUID errors:**
- Use `sqlalchemy.dialects.postgresql.UUID` with `as_uuid=True`
- Import `from uuid import uuid4` for default factory
