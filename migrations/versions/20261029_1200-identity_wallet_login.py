"""Store Wallet Identity DID and current identity authorization state.

Revision ID: 20261029_identity_wallet_login
Revises: d72569034d1a
Create Date: 2026-10-29 12:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261029_identity_wallet_login"
down_revision: Union[str, None] = "d72569034d1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("wallet_users", sa.Column("identity_did", sa.String(length=255), nullable=True))
    op.create_index("ix_wallet_users_identity_did", "wallet_users", ["identity_did"], unique=True)
    op.add_column("passport_login_sessions", sa.Column("state", sa.String(length=128), nullable=True))
    op.create_index("ix_passport_login_sessions_state", "passport_login_sessions", ["state"], unique=True)
    op.add_column("passport_login_sessions", sa.Column("audience", sa.String(length=1024), nullable=True))
    op.add_column("passport_login_sessions", sa.Column("nonce", sa.String(length=255), nullable=True))
    op.add_column("passport_login_sessions", sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("passport_login_sessions", sa.Column("identity_did", sa.String(length=255), nullable=True))
    op.create_index("ix_passport_login_sessions_identity_did", "passport_login_sessions", ["identity_did"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_passport_login_sessions_identity_did", table_name="passport_login_sessions")
    op.drop_column("passport_login_sessions", "identity_did")
    op.drop_column("passport_login_sessions", "scopes")
    op.drop_column("passport_login_sessions", "nonce")
    op.drop_column("passport_login_sessions", "audience")
    op.drop_index("ix_passport_login_sessions_state", table_name="passport_login_sessions")
    op.drop_column("passport_login_sessions", "state")
    op.drop_index("ix_wallet_users_identity_did", table_name="wallet_users")
    op.drop_column("wallet_users", "identity_did")
