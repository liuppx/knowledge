"""Publish knowledge items to the KnowDoGraph (知行图) chain.

Adds what the chain needs and Knowledge did not record: the language of a revision,
which model generated it, the item's chain domain / layer, item-to-item relations
(basis / see-also / supersedes), and a record of each publication. Signing happens in
the user's wallet in the browser; nothing here stores keys.

Revision ID: 20261120_kdg_publication
Revises: 20261119_tool_credential_index
Create Date: 2026-11-20 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261120_kdg_publication"
down_revision = "20261119_tool_credential_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_items", sa.Column("kdg_domain", sa.Integer(), nullable=True))
    op.add_column("knowledge_items", sa.Column("kdg_layer", sa.String(length=32), nullable=True))
    op.add_column(
        "knowledge_item_revisions",
        sa.Column("language", sa.String(length=16), nullable=False, server_default="zh"),
    )
    op.add_column(
        "knowledge_item_revisions",
        sa.Column("generated_by_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.create_table(
        "knowledge_item_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("from_item_id", sa.Integer(), sa.ForeignKey("knowledge_items.id"), nullable=False),
        sa.Column("to_item_id", sa.Integer(), sa.ForeignKey("knowledge_items.id"), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("from_item_id", "to_item_id", "kind", name="uq_item_relation_from_to_kind"),
    )
    op.create_index("ix_knowledge_item_relations_from_item_id", "knowledge_item_relations", ["from_item_id"])
    op.create_index("ix_knowledge_item_relations_to_item_id", "knowledge_item_relations", ["to_item_id"])

    op.create_table(
        "kdg_publications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("revision_id", sa.Integer(), sa.ForeignKey("knowledge_item_revisions.id"), nullable=False),
        sa.Column("kb_id", sa.Integer(), sa.ForeignKey("knowledge_bases.id"), nullable=False),
        sa.Column("network", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("op_type", sa.String(length=24), nullable=False),
        sa.Column("chain_unit", sa.Integer(), nullable=True),
        sa.Column("chain_version", sa.Integer(), nullable=True),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("body_url", sa.String(length=255), nullable=False),
        sa.Column("op_hash", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.Integer(), nullable=True),
        sa.Column("actor_pubkey", sa.String(length=64), nullable=False),
        sa.Column("intent_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_kdg_publications_revision_id", "kdg_publications", ["revision_id"])
    op.create_index("ix_kdg_publications_kb_id", "kdg_publications", ["kb_id"])
    op.create_index("ix_kdg_publications_revision_status", "kdg_publications", ["revision_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_kdg_publications_revision_status", table_name="kdg_publications")
    op.drop_index("ix_kdg_publications_kb_id", table_name="kdg_publications")
    op.drop_index("ix_kdg_publications_revision_id", table_name="kdg_publications")
    op.drop_table("kdg_publications")
    op.drop_index("ix_knowledge_item_relations_to_item_id", table_name="knowledge_item_relations")
    op.drop_index("ix_knowledge_item_relations_from_item_id", table_name="knowledge_item_relations")
    op.drop_table("knowledge_item_relations")
    op.drop_column("knowledge_item_revisions", "generated_by_json")
    op.drop_column("knowledge_item_revisions", "language")
    op.drop_column("knowledge_items", "kdg_layer")
    op.drop_column("knowledge_items", "kdg_domain")
