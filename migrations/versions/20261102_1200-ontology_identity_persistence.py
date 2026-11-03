"""persist ontology identity review and evidence records

Revision ID: 20261102_ontology_identity
Revises: 20261029_identity_wallet_login
Create Date: 2026-11-02 12:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261102_ontology_identity"
down_revision: Union[str, None] = "20261029_identity_wallet_login"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_knowledge_bases_id_owner_wallet", "knowledge_bases", ["id", "owner_wallet_address"]
    )

    op.create_table(
        "ontology_evidence_references",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("uri", sa.String(length=2048), nullable=False),
        sa.Column("source_version", sa.String(length=255), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["kb_id", "owner_wallet_address"],
            ["knowledge_bases.id", "knowledge_bases.owner_wallet_address"],
            name="fk_ontology_evidence_knowledge_base_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "kb_id", "owner_wallet_address", name="uq_ontology_evidence_scope"),
    )
    op.create_index("ix_ontology_evidence_references_kb_id", "ontology_evidence_references", ["kb_id"])
    op.create_index(
        "ix_ontology_evidence_references_owner_wallet_address",
        "ontology_evidence_references",
        ["owner_wallet_address"],
    )
    op.create_index(
        "ix_ontology_evidence_kb_checksum", "ontology_evidence_references", ["kb_id", "checksum"]
    )

    op.create_table(
        "ontology_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=False),
        sa.Column("identity_status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "object_type IN ('contract', 'product', 'organization')", name="ck_ontology_objects_type"
        ),
        sa.CheckConstraint(
            "identity_status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_objects_identity_status",
        ),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["kb_id", "owner_wallet_address"],
            ["knowledge_bases.id", "knowledge_bases.owner_wallet_address"],
            name="fk_ontology_objects_knowledge_base_owner",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "kb_id", "owner_wallet_address", name="uq_ontology_objects_scope"),
    )
    op.create_index("ix_ontology_objects_kb_id", "ontology_objects", ["kb_id"])
    op.create_index("ix_ontology_objects_owner_wallet_address", "ontology_objects", ["owner_wallet_address"])
    op.create_index(
        "ix_ontology_objects_kb_status_created", "ontology_objects", ["kb_id", "identity_status", "created_at"]
    )

    op.create_table(
        "ontology_external_identifiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=1024), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("registered_by", sa.String(length=64), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_identifier_object_scope",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_identifier_evidence_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kb_id", "namespace", "value", name="uq_ontology_external_identifier_kb_namespace_value"
        ),
    )
    op.create_index("ix_ontology_external_identifiers_kb_id", "ontology_external_identifiers", ["kb_id"])
    op.create_index(
        "ix_ontology_external_identifiers_owner_wallet_address",
        "ontology_external_identifiers",
        ["owner_wallet_address"],
    )
    op.create_index(
        "ix_ontology_identifiers_object", "ontology_external_identifiers", ["object_id", "kb_id"]
    )

    op.create_table(
        "ontology_identity_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=64), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_reviews_status",
        ),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_review_object_scope",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_review_evidence_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ontology_identity_reviews_kb_id", "ontology_identity_reviews", ["kb_id"])
    op.create_index(
        "ix_ontology_identity_reviews_owner_wallet_address", "ontology_identity_reviews", ["owner_wallet_address"]
    )
    op.create_index(
        "ix_ontology_reviews_object_reviewed", "ontology_identity_reviews", ["object_id", "reviewed_at"]
    )

    op.create_table(
        "ontology_crosswalks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=False),
        sa.Column("source_value", sa.String(length=1024), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("canonical_namespace", sa.String(length=255), nullable=False),
        sa.Column("canonical_value", sa.String(length=1024), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_crosswalk_object_scope",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_crosswalk_evidence_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kb_id", "namespace", "source_value", name="uq_ontology_crosswalk_source"),
    )
    op.create_index("ix_ontology_crosswalks_kb_id", "ontology_crosswalks", ["kb_id"])
    op.create_index("ix_ontology_crosswalks_owner_wallet_address", "ontology_crosswalks", ["owner_wallet_address"])
    op.create_index("ix_ontology_crosswalks_object", "ontology_crosswalks", ["object_id", "kb_id"])
    op.create_index(
        "ix_ontology_crosswalks_canonical",
        "ontology_crosswalks",
        ["kb_id", "canonical_namespace", "canonical_value"],
    )

    op.create_table(
        "ontology_identifier_conflicts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("existing_object_id", sa.String(length=36), nullable=False),
        sa.Column("claimant_object_id", sa.String(length=36), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("existing_prior_status", sa.String(length=32), nullable=False),
        sa.Column("claimant_prior_status", sa.String(length=32), nullable=False),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("existing_object_id <> claimant_object_id", name="ck_ontology_conflict_distinct_objects"),
        sa.CheckConstraint("status IN ('open', 'claim_rejected')", name="ck_ontology_conflicts_status"),
        sa.CheckConstraint(
            "existing_prior_status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_conflicts_existing_prior_status",
        ),
        sa.CheckConstraint(
            "claimant_prior_status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_conflicts_claimant_prior_status",
        ),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["existing_object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_conflict_existing_object_scope",
        ),
        sa.ForeignKeyConstraint(
            ["claimant_object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_conflict_claimant_object_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "kb_id", "owner_wallet_address", name="uq_ontology_conflict_scope"),
        sa.UniqueConstraint(
            "kb_id",
            "existing_object_id",
            "claimant_object_id",
            "namespace",
            "value",
            name="uq_ontology_identifier_conflict_pair",
        ),
    )
    op.create_index("ix_ontology_identifier_conflicts_kb_id", "ontology_identifier_conflicts", ["kb_id"])
    op.create_index(
        "ix_ontology_identifier_conflicts_owner_wallet_address",
        "ontology_identifier_conflicts",
        ["owner_wallet_address"],
    )
    op.create_index(
        "ix_ontology_conflicts_kb_status_reported",
        "ontology_identifier_conflicts",
        ["kb_id", "status", "reported_at"],
    )

    op.create_table(
        "ontology_identifier_conflict_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conflict_id", sa.String(length=36), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("reported_by", sa.String(length=64), nullable=False),
        sa.Column("reported_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["conflict_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_identifier_conflicts.id",
                "ontology_identifier_conflicts.kb_id",
                "ontology_identifier_conflicts.owner_wallet_address",
            ],
            name="fk_ontology_conflict_report_conflict_scope",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_conflict_report_evidence_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conflict_id", "evidence_id", "reported_by", name="uq_ontology_conflict_report_idempotency"
        ),
    )
    op.create_index(
        "ix_ontology_identifier_conflict_reports_kb_id", "ontology_identifier_conflict_reports", ["kb_id"]
    )
    op.create_index(
        "ix_ontology_identifier_conflict_reports_owner_wallet_address",
        "ontology_identifier_conflict_reports",
        ["owner_wallet_address"],
    )
    op.create_index(
        "ix_ontology_conflict_reports_conflict",
        "ontology_identifier_conflict_reports",
        ["conflict_id", "reported_at"],
    )

    op.create_table(
        "ontology_conflict_resolutions",
        sa.Column("conflict_id", sa.String(length=36), nullable=False),
        sa.Column("kb_id", sa.Integer(), nullable=False),
        sa.Column("owner_wallet_address", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("adjudicated_by", sa.String(length=64), nullable=False),
        sa.Column("adjudicated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("decision = 'claim_rejected'", name="ck_ontology_conflict_resolution_decision"),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(
            ["conflict_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_identifier_conflicts.id",
                "ontology_identifier_conflicts.kb_id",
                "ontology_identifier_conflicts.owner_wallet_address",
            ],
            name="fk_ontology_conflict_resolution_conflict_scope",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_conflict_resolution_evidence_scope",
        ),
        sa.PrimaryKeyConstraint("conflict_id"),
    )
    op.create_index("ix_ontology_conflict_resolutions_kb_id", "ontology_conflict_resolutions", ["kb_id"])
    op.create_index(
        "ix_ontology_conflict_resolutions_owner_wallet_address",
        "ontology_conflict_resolutions",
        ["owner_wallet_address"],
    )


def downgrade() -> None:
    op.drop_index("ix_ontology_conflict_resolutions_owner_wallet_address", table_name="ontology_conflict_resolutions")
    op.drop_index("ix_ontology_conflict_resolutions_kb_id", table_name="ontology_conflict_resolutions")
    op.drop_table("ontology_conflict_resolutions")

    op.drop_index("ix_ontology_conflict_reports_conflict", table_name="ontology_identifier_conflict_reports")
    op.drop_index(
        "ix_ontology_identifier_conflict_reports_owner_wallet_address",
        table_name="ontology_identifier_conflict_reports",
    )
    op.drop_index("ix_ontology_identifier_conflict_reports_kb_id", table_name="ontology_identifier_conflict_reports")
    op.drop_table("ontology_identifier_conflict_reports")

    op.drop_index("ix_ontology_conflicts_kb_status_reported", table_name="ontology_identifier_conflicts")
    op.drop_index(
        "ix_ontology_identifier_conflicts_owner_wallet_address", table_name="ontology_identifier_conflicts"
    )
    op.drop_index("ix_ontology_identifier_conflicts_kb_id", table_name="ontology_identifier_conflicts")
    op.drop_table("ontology_identifier_conflicts")

    op.drop_index("ix_ontology_crosswalks_canonical", table_name="ontology_crosswalks")
    op.drop_index("ix_ontology_crosswalks_object", table_name="ontology_crosswalks")
    op.drop_index("ix_ontology_crosswalks_owner_wallet_address", table_name="ontology_crosswalks")
    op.drop_index("ix_ontology_crosswalks_kb_id", table_name="ontology_crosswalks")
    op.drop_table("ontology_crosswalks")

    op.drop_index("ix_ontology_reviews_object_reviewed", table_name="ontology_identity_reviews")
    op.drop_index("ix_ontology_identity_reviews_owner_wallet_address", table_name="ontology_identity_reviews")
    op.drop_index("ix_ontology_identity_reviews_kb_id", table_name="ontology_identity_reviews")
    op.drop_table("ontology_identity_reviews")

    op.drop_index("ix_ontology_identifiers_object", table_name="ontology_external_identifiers")
    op.drop_index(
        "ix_ontology_external_identifiers_owner_wallet_address", table_name="ontology_external_identifiers"
    )
    op.drop_index("ix_ontology_external_identifiers_kb_id", table_name="ontology_external_identifiers")
    op.drop_table("ontology_external_identifiers")

    op.drop_index("ix_ontology_objects_kb_status_created", table_name="ontology_objects")
    op.drop_index("ix_ontology_objects_owner_wallet_address", table_name="ontology_objects")
    op.drop_index("ix_ontology_objects_kb_id", table_name="ontology_objects")
    op.drop_table("ontology_objects")

    op.drop_index("ix_ontology_evidence_kb_checksum", table_name="ontology_evidence_references")
    op.drop_index(
        "ix_ontology_evidence_references_owner_wallet_address", table_name="ontology_evidence_references"
    )
    op.drop_index("ix_ontology_evidence_references_kb_id", table_name="ontology_evidence_references")
    op.drop_table("ontology_evidence_references")
    op.drop_constraint("uq_knowledge_bases_id_owner_wallet", "knowledge_bases", type_="unique")
