"""Record retry lineage on agent runs.

Revision ID: 20261107_agent_run_retry
Revises: 20261102_ontology_identity
Create Date: 2026-11-07 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261107_agent_run_retry"
down_revision = "20261102_ontology_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("retry_of_run_id", sa.String(length=64), nullable=True))
    op.add_column("agent_runs", sa.Column("attempt", sa.Integer(), server_default="1", nullable=False))
    op.create_foreign_key(
        "fk_agent_runs_retry_of_run_id", "agent_runs", "agent_runs", ["retry_of_run_id"], ["id"]
    )
    op.create_unique_constraint("uq_agent_runs_retry_of_run_id", "agent_runs", ["retry_of_run_id"])


def downgrade() -> None:
    op.drop_constraint("uq_agent_runs_retry_of_run_id", "agent_runs", type_="unique")
    op.drop_constraint("fk_agent_runs_retry_of_run_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "attempt")
    op.drop_column("agent_runs", "retry_of_run_id")
