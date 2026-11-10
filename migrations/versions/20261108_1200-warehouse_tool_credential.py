"""Persist scoped Warehouse Tool credentials for asynchronous Knowledge runs.

Revision ID: 20261108_tool_credential
Revises: 20261107_agent_run_retry
Create Date: 2026-11-08 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261108_tool_credential"
down_revision = "20261107_agent_run_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_tool_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False, unique=True),
        sa.Column("warehouse_credential_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("path_prefixes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_warehouse_tool_credentials_owner_wallet_address",
        "warehouse_tool_credentials",
        ["owner_wallet_address"],
    )


def downgrade() -> None:
    op.drop_index("ix_warehouse_tool_credentials_owner_wallet_address", table_name="warehouse_tool_credentials")
    op.drop_table("warehouse_tool_credentials")
