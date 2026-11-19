"""Align warehouse_tool_credentials.owner_wallet_address with the model.

The model declares owner_wallet_address as ``unique=True, index=True``, i.e. one
unique index. Migration 20261108_tool_credential instead created a column-level
unique constraint plus a separate non-unique index, so ``alembic check`` reports
drift on every fresh database. Replace the pair with the single unique index the
model expects. Uniqueness is enforced throughout: the unique index is created
before the old constraint is dropped.

Revision ID: 20261119_tool_credential_index
Revises: 20261108_tool_credential
Create Date: 2026-11-19 12:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20261119_tool_credential_index"
down_revision = "20261108_tool_credential"
branch_labels = None
depends_on = None

TABLE = "warehouse_tool_credentials"
INDEX = "ix_warehouse_tool_credentials_owner_wallet_address"
CONSTRAINT = "warehouse_tool_credentials_owner_wallet_address_key"
TMP_INDEX = "ix_warehouse_tool_credentials_owner_wallet_address_unique_tmp"


def upgrade() -> None:
    op.create_index(TMP_INDEX, TABLE, ["owner_wallet_address"], unique=True)
    op.drop_constraint(CONSTRAINT, TABLE, type_="unique")
    op.drop_index(INDEX, table_name=TABLE)
    op.execute(f"ALTER INDEX {TMP_INDEX} RENAME TO {INDEX}")


def downgrade() -> None:
    op.create_unique_constraint(CONSTRAINT, TABLE, ["owner_wallet_address"])
    op.drop_index(INDEX, table_name=TABLE)
    op.create_index(INDEX, TABLE, ["owner_wallet_address"])
