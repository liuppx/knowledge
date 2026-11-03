from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from knowledge.db.base import Base
from knowledge.models.entities import utcnow


ONTOLOGY_OBJECT_TYPES = ("contract", "product", "organization")
ONTOLOGY_IDENTITY_STATUSES = (
    "candidate",
    "confirmed",
    "ambiguous",
    "insufficient_evidence",
)
ONTOLOGY_CONFLICT_STATUSES = ("open", "claim_rejected")


class OntologyEvidenceReference(Base):
    __tablename__ = "ontology_evidence_references"
    __table_args__ = (
        UniqueConstraint("id", "kb_id", "owner_wallet_address", name="uq_ontology_evidence_scope"),
        ForeignKeyConstraint(
            ["kb_id", "owner_wallet_address"],
            ["knowledge_bases.id", "knowledge_bases.owner_wallet_address"],
            name="fk_ontology_evidence_knowledge_base_owner",
        ),
        Index("ix_ontology_evidence_kb_checksum", "kb_id", "checksum"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_version: Mapped[str] = mapped_column(String(255), nullable=False)
    locator: Mapped[str] = mapped_column(Text, default="", nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OntologyObject(Base):
    __tablename__ = "ontology_objects"
    __table_args__ = (
        UniqueConstraint("id", "kb_id", "owner_wallet_address", name="uq_ontology_objects_scope"),
        ForeignKeyConstraint(
            ["kb_id", "owner_wallet_address"],
            ["knowledge_bases.id", "knowledge_bases.owner_wallet_address"],
            name="fk_ontology_objects_knowledge_base_owner",
        ),
        CheckConstraint(
            "object_type IN ('contract', 'product', 'organization')",
            name="ck_ontology_objects_type",
        ),
        CheckConstraint(
            "identity_status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_objects_identity_status",
        ),
        Index("ix_ontology_objects_kb_status_created", "kb_id", "identity_status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    identity_status: Mapped[str] = mapped_column(String(32), default="candidate", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class OntologyExternalIdentifier(Base):
    __tablename__ = "ontology_external_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "kb_id", "namespace", "value", name="uq_ontology_external_identifier_kb_namespace_value"
        ),
        ForeignKeyConstraint(
            ["object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_identifier_object_scope",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_identifier_evidence_scope",
        ),
        Index("ix_ontology_identifiers_object", "object_id", "kb_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    registered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OntologyIdentityReview(Base):
    __tablename__ = "ontology_identity_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_reviews_status",
        ),
        ForeignKeyConstraint(
            ["object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_review_object_scope",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_review_evidence_scope",
        ),
        Index("ix_ontology_reviews_object_reviewed", "object_id", "reviewed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OntologyCrosswalk(Base):
    __tablename__ = "ontology_crosswalks"
    __table_args__ = (
        UniqueConstraint(
            "kb_id", "namespace", "source_value", name="uq_ontology_crosswalk_source"
        ),
        ForeignKeyConstraint(
            ["object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_crosswalk_object_scope",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_crosswalk_evidence_scope",
        ),
        Index("ix_ontology_crosswalks_object", "object_id", "kb_id"),
        Index("ix_ontology_crosswalks_canonical", "kb_id", "canonical_namespace", "canonical_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    source_value: Mapped[str] = mapped_column(String(1024), nullable=False)
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(1024), nullable=False)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OntologyIdentifierConflict(Base):
    __tablename__ = "ontology_identifier_conflicts"
    __table_args__ = (
        UniqueConstraint("id", "kb_id", "owner_wallet_address", name="uq_ontology_conflict_scope"),
        UniqueConstraint(
            "kb_id",
            "existing_object_id",
            "claimant_object_id",
            "namespace",
            "value",
            name="uq_ontology_identifier_conflict_pair",
        ),
        CheckConstraint("existing_object_id <> claimant_object_id", name="ck_ontology_conflict_distinct_objects"),
        CheckConstraint("status IN ('open', 'claim_rejected')", name="ck_ontology_conflicts_status"),
        CheckConstraint(
            "existing_prior_status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_conflicts_existing_prior_status",
        ),
        CheckConstraint(
            "claimant_prior_status IN ('candidate', 'confirmed', 'ambiguous', 'insufficient_evidence')",
            name="ck_ontology_conflicts_claimant_prior_status",
        ),
        ForeignKeyConstraint(
            ["existing_object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_conflict_existing_object_scope",
        ),
        ForeignKeyConstraint(
            ["claimant_object_id", "kb_id", "owner_wallet_address"],
            ["ontology_objects.id", "ontology_objects.kb_id", "ontology_objects.owner_wallet_address"],
            name="fk_ontology_conflict_claimant_object_scope",
        ),
        Index("ix_ontology_conflicts_kb_status_reported", "kb_id", "status", "reported_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    existing_object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    claimant_object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    existing_prior_status: Mapped[str] = mapped_column(String(32), nullable=False)
    claimant_prior_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OntologyIdentifierConflictReport(Base):
    __tablename__ = "ontology_identifier_conflict_reports"
    __table_args__ = (
        UniqueConstraint(
            "conflict_id", "evidence_id", "reported_by", name="uq_ontology_conflict_report_idempotency"
        ),
        ForeignKeyConstraint(
            ["conflict_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_identifier_conflicts.id",
                "ontology_identifier_conflicts.kb_id",
                "ontology_identifier_conflicts.owner_wallet_address",
            ],
            name="fk_ontology_conflict_report_conflict_scope",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_conflict_report_evidence_scope",
        ),
        Index("ix_ontology_conflict_reports_conflict", "conflict_id", "reported_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conflict_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reported_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OntologyConflictResolution(Base):
    __tablename__ = "ontology_conflict_resolutions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conflict_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_identifier_conflicts.id",
                "ontology_identifier_conflicts.kb_id",
                "ontology_identifier_conflicts.owner_wallet_address",
            ],
            name="fk_ontology_conflict_resolution_conflict_scope",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "kb_id", "owner_wallet_address"],
            [
                "ontology_evidence_references.id",
                "ontology_evidence_references.kb_id",
                "ontology_evidence_references.owner_wallet_address",
            ],
            name="fk_ontology_conflict_resolution_evidence_scope",
        ),
        CheckConstraint("decision = 'claim_rejected'", name="ck_ontology_conflict_resolution_decision"),
    )

    conflict_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), index=True, nullable=False)
    owner_wallet_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_id: Mapped[int] = mapped_column(Integer, nullable=False)
    adjudicated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    adjudicated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
