"""§2.3b — a fresh, empty database must build cleanly from the migration chain.
Creates a throwaway DB, runs `alembic upgrade head` against it, asserts the live
schema is reproduced, then drops it. Skips if Postgres isn't reachable (e.g. CI
without a DB), so it never blocks the rest of the suite.
"""
import os
import uuid

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
_DB_URL = os.environ.get("DATABASE_URL", "")


def _admin_engine(prefix: str, base_db: str):
    # AUTOCOMMIT: CREATE/DROP DATABASE cannot run inside a transaction.
    return create_engine(f"{prefix}/{base_db}", isolation_level="AUTOCOMMIT")


@pytest.mark.skipif(not _DB_URL.startswith("postgresql"), reason="no Postgres DATABASE_URL")
def test_migrations_upgrade_clean_on_empty_db():
    from alembic.config import Config
    from alembic import command

    prefix, _, base_db = _DB_URL.rpartition("/")
    tmp = f"test_migr_{uuid.uuid4().hex[:8]}"

    try:
        admin = _admin_engine(prefix, base_db)
        with admin.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres not reachable")

    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{tmp}"'))

    tmp_url = f"{prefix}/{tmp}"
    prev = os.environ.get("DATABASE_URL")
    try:
        # alembic/env.py reads DATABASE_URL from the environment (load_dotenv does
        # not override an already-set var), so point it at the throwaway DB.
        os.environ["DATABASE_URL"] = tmp_url
        command.upgrade(Config("alembic.ini"), "head")

        eng = create_engine(tmp_url)
        with eng.connect() as c:
            tables = {r[0] for r in c.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
            ))}
            # core tables from across the whole migration chain
            assert {"programs", "assets", "findings", "hunt_sessions",
                    "http_exchanges", "recon_runs", "alembic_version"} <= tables

            prog_cols = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='programs'"
            ))}
            assert "compliance" in prog_cols          # from the latest migration

            ex_cols = {r[0] for r in c.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='http_exchanges'"
            ))}
            assert {"finding_id", "is_evidence"} <= ex_cols   # evidence columns

            version = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "e7c1a9d3f5b2"          # stamped at head
        eng.dispose()
    finally:
        if prev is not None:
            os.environ["DATABASE_URL"] = prev
        # terminate any lingering connections, then drop the throwaway DB
        with admin.connect() as c:
            c.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{tmp}' AND pid <> pg_backend_pid()"
            ))
            c.execute(text(f'DROP DATABASE IF EXISTS "{tmp}"'))
        admin.dispose()
