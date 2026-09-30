from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from knowledge.db.session import engine


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    """Build an Alembic config with absolute paths.

    Absolute paths keep migrations working regardless of the process working
    directory (systemd units, workers, CI). The database URL is resolved inside
    migrations/env.py from knowledge.core.settings, so it is not set here.
    """
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    return config


def upgrade_to_head() -> None:
    """Apply all pending migrations. Safe to call on every process startup."""
    command.upgrade(alembic_config(), "head")


def stamp_head() -> None:
    """Mark the database as being at the latest revision without running DDL.

    Used by the test harness after it builds the schema directly from the models
    via ``Base.metadata.create_all``, so the app startup's schema bootstrap
    becomes a no-op instead of re-running the initial CREATE TABLE statements.
    """
    command.stamp(alembic_config(), "head")


def ensure_database_schema() -> None:
    """Bring the schema to head safely, called on every process startup.

    Handles three cases:
    - Fresh/empty database: run migrations to create everything.
    - Already Alembic-managed database: apply any pending migrations.
    - Pre-Alembic database (tables created by the old ``create_all`` path, with
      no ``alembic_version`` table): adopt it by stamping head, so the transition
      to Alembic does not fail on existing deployments.
    """
    tables = set(inspect(engine).get_table_names())
    pre_alembic = bool(tables - {"alembic_version"}) and "alembic_version" not in tables
    if pre_alembic:
        stamp_head()
    else:
        upgrade_to_head()
