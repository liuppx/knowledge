from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from knowledge.models import KnowledgeBase
from knowledge.models.ontology import (
    OntologyConflictResolution,
    OntologyCrosswalk,
    OntologyEvidenceReference,
    OntologyExternalIdentifier,
    OntologyIdentifierConflict,
    OntologyIdentifierConflictReport,
    OntologyIdentityReview,
    OntologyObject,
)


class OntologyError(Exception):
    status_code = 400


class OntologyNotFound(OntologyError):
    status_code = 404


class OntologyInvalidOperation(OntologyError):
    status_code = 422


class OntologyConflictError(OntologyError):
    status_code = 409


class OntologyService:
    """Owner-scoped persistence for the reviewed identity workflow."""

    @staticmethod
    def _require_kb(db: Session, kb_id: int, wallet_address: str) -> None:
        exists = db.scalar(
            select(KnowledgeBase.id).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.owner_wallet_address == wallet_address,
            )
        )
        if exists is None:
            raise OntologyNotFound("knowledge base not found")

    @staticmethod
    def _get_evidence(db: Session, kb_id: int, wallet_address: str, evidence_id: int) -> OntologyEvidenceReference:
        evidence = db.scalar(
            select(OntologyEvidenceReference).where(
                OntologyEvidenceReference.id == evidence_id,
                OntologyEvidenceReference.kb_id == kb_id,
                OntologyEvidenceReference.owner_wallet_address == wallet_address,
            )
        )
        if evidence is None:
            raise OntologyNotFound("evidence reference not found")
        return evidence

    @staticmethod
    def _get_object(
        db: Session, kb_id: int, wallet_address: str, object_id: str, *, lock: bool = False
    ) -> OntologyObject:
        query = select(OntologyObject).where(
            OntologyObject.id == object_id,
            OntologyObject.kb_id == kb_id,
            OntologyObject.owner_wallet_address == wallet_address,
        )
        if lock:
            query = query.with_for_update()
        record = db.scalar(query)
        if record is None:
            raise OntologyNotFound("ontology object not found")
        return record

    @staticmethod
    def _get_conflict(
        db: Session, kb_id: int, wallet_address: str, conflict_id: str, *, lock: bool = False
    ) -> OntologyIdentifierConflict:
        query = select(OntologyIdentifierConflict).where(
            OntologyIdentifierConflict.id == conflict_id,
            OntologyIdentifierConflict.kb_id == kb_id,
            OntologyIdentifierConflict.owner_wallet_address == wallet_address,
        )
        if lock:
            query = query.with_for_update()
        conflict = db.scalar(query)
        if conflict is None:
            raise OntologyNotFound("identity conflict not found")
        return conflict

    @staticmethod
    def _open_conflicts(db: Session, kb_id: int, wallet_address: str, object_id: str) -> list[OntologyIdentifierConflict]:
        return list(
            db.scalars(
                select(OntologyIdentifierConflict)
                .where(
                    OntologyIdentifierConflict.kb_id == kb_id,
                    OntologyIdentifierConflict.owner_wallet_address == wallet_address,
                    OntologyIdentifierConflict.status == "open",
                    or_(
                        OntologyIdentifierConflict.existing_object_id == object_id,
                        OntologyIdentifierConflict.claimant_object_id == object_id,
                    ),
                )
                .order_by(OntologyIdentifierConflict.reported_at, OntologyIdentifierConflict.id)
            ).all()
        )

    @classmethod
    def _prior_status(
        cls, db: Session, kb_id: int, wallet_address: str, object_id: str, current_status: str
    ) -> str:
        conflicts = cls._open_conflicts(db, kb_id, wallet_address, object_id)
        if not conflicts:
            return current_status
        conflict = conflicts[0]
        if conflict.existing_object_id == object_id:
            return conflict.existing_prior_status
        return conflict.claimant_prior_status

    @staticmethod
    def _serialize_object(db: Session, record: OntologyObject) -> dict:
        scope = (
            OntologyExternalIdentifier.kb_id == record.kb_id,
            OntologyExternalIdentifier.owner_wallet_address == record.owner_wallet_address,
            OntologyExternalIdentifier.object_id == record.id,
        )
        identifiers = db.scalars(
            select(OntologyExternalIdentifier).where(*scope).order_by(OntologyExternalIdentifier.id)
        ).all()
        reviews = db.scalars(
            select(OntologyIdentityReview)
            .where(
                OntologyIdentityReview.kb_id == record.kb_id,
                OntologyIdentityReview.owner_wallet_address == record.owner_wallet_address,
                OntologyIdentityReview.object_id == record.id,
            )
            .order_by(OntologyIdentityReview.reviewed_at, OntologyIdentityReview.id)
        ).all()
        crosswalks = db.scalars(
            select(OntologyCrosswalk)
            .where(
                OntologyCrosswalk.kb_id == record.kb_id,
                OntologyCrosswalk.owner_wallet_address == record.owner_wallet_address,
                OntologyCrosswalk.object_id == record.id,
            )
            .order_by(OntologyCrosswalk.created_at, OntologyCrosswalk.id)
        ).all()
        return {
            "id": record.id,
            "kb_id": record.kb_id,
            "object_type": record.object_type,
            "label": record.label,
            "identity_status": record.identity_status,
            "created_by": record.created_by,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "identifiers": identifiers,
            "reviews": reviews,
            "crosswalks": crosswalks,
        }

    @classmethod
    def _serialize_conflict(cls, db: Session, conflict: OntologyIdentifierConflict) -> dict:
        reports = db.scalars(
            select(OntologyIdentifierConflictReport)
            .where(
                OntologyIdentifierConflictReport.conflict_id == conflict.id,
                OntologyIdentifierConflictReport.kb_id == conflict.kb_id,
                OntologyIdentifierConflictReport.owner_wallet_address == conflict.owner_wallet_address,
            )
            .order_by(OntologyIdentifierConflictReport.reported_at, OntologyIdentifierConflictReport.id)
        ).all()
        resolution = db.scalar(
            select(OntologyConflictResolution).where(
                OntologyConflictResolution.conflict_id == conflict.id,
                OntologyConflictResolution.kb_id == conflict.kb_id,
                OntologyConflictResolution.owner_wallet_address == conflict.owner_wallet_address,
            )
        )
        return {
            "id": conflict.id,
            "kb_id": conflict.kb_id,
            "existing_object_id": conflict.existing_object_id,
            "claimant_object_id": conflict.claimant_object_id,
            "namespace": conflict.namespace,
            "value": conflict.value,
            "status": conflict.status,
            "reported_at": conflict.reported_at,
            "reports": reports,
            "resolution": resolution,
        }

    @staticmethod
    def _commit(db: Session) -> None:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    def create_evidence(
        self, db: Session, wallet_address: str, kb_id: int, *, uri: str, source_version: str,
        locator: str = "", checksum: str = "",
    ) -> OntologyEvidenceReference:
        self._require_kb(db, kb_id, wallet_address)
        normalized_uri = uri.strip()
        normalized_version = source_version.strip()
        if not normalized_uri or not normalized_version:
            raise OntologyInvalidOperation("evidence uri and source_version are required")
        record = OntologyEvidenceReference(
            kb_id=kb_id,
            owner_wallet_address=wallet_address,
            uri=normalized_uri,
            source_version=normalized_version,
            locator=locator.strip(),
            checksum=checksum.strip(),
            created_by=wallet_address,
        )
        db.add(record)
        self._commit(db)
        db.refresh(record)
        return record

    def create_object(
        self, db: Session, wallet_address: str, kb_id: int, *, object_type: str, label: str, evidence_id: int
    ) -> dict:
        self._require_kb(db, kb_id, wallet_address)
        evidence = self._get_evidence(db, kb_id, wallet_address, evidence_id)
        normalized_label = label.strip()
        if not normalized_label:
            raise OntologyInvalidOperation("object label is required")
        record = OntologyObject(
            kb_id=kb_id,
            owner_wallet_address=wallet_address,
            object_type=object_type,
            label=normalized_label,
            identity_status="candidate",
            created_by=wallet_address,
        )
        db.add(record)
        db.flush()
        db.add(
            OntologyIdentityReview(
                object_id=record.id,
                kb_id=kb_id,
                owner_wallet_address=wallet_address,
                status="candidate",
                rationale="Object created for identity review.",
                evidence_id=evidence.id,
                reviewed_by=wallet_address,
            )
        )
        self._commit(db)
        db.refresh(record)
        return self._serialize_object(db, record)

    def list_objects(
        self, db: Session, wallet_address: str, kb_id: int, *, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        self._require_kb(db, kb_id, wallet_address)
        records = db.scalars(
            select(OntologyObject)
            .where(
                OntologyObject.kb_id == kb_id,
                OntologyObject.owner_wallet_address == wallet_address,
            )
            .order_by(OntologyObject.created_at.desc(), OntologyObject.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [self._serialize_object(db, record) for record in records]

    def get_object(self, db: Session, wallet_address: str, kb_id: int, object_id: str) -> dict:
        self._require_kb(db, kb_id, wallet_address)
        return self._serialize_object(db, self._get_object(db, kb_id, wallet_address, object_id))

    def register_identifier(
        self, db: Session, wallet_address: str, kb_id: int, object_id: str, *, namespace: str, value: str,
        evidence_id: int,
    ) -> OntologyExternalIdentifier:
        self._require_kb(db, kb_id, wallet_address)
        self._get_object(db, kb_id, wallet_address, object_id, lock=True)
        self._get_evidence(db, kb_id, wallet_address, evidence_id)
        normalized_namespace, normalized_value = namespace.strip(), value.strip()
        if not normalized_namespace or not normalized_value:
            raise OntologyInvalidOperation("identifier namespace and value are required")
        existing = db.scalar(
            select(OntologyExternalIdentifier).where(
                OntologyExternalIdentifier.kb_id == kb_id,
                OntologyExternalIdentifier.owner_wallet_address == wallet_address,
                OntologyExternalIdentifier.namespace == normalized_namespace,
                OntologyExternalIdentifier.value == normalized_value,
            )
        )
        if existing is not None:
            if existing.object_id != object_id:
                raise OntologyConflictError("external identifier is already assigned to another object")
            if existing.evidence_id != evidence_id:
                raise OntologyConflictError("external identifier is already registered with different evidence")
            return existing
        record = OntologyExternalIdentifier(
            object_id=object_id,
            kb_id=kb_id,
            owner_wallet_address=wallet_address,
            namespace=normalized_namespace,
            value=normalized_value,
            evidence_id=evidence_id,
            registered_by=wallet_address,
        )
        db.add(record)
        try:
            self._commit(db)
        except IntegrityError as exc:
            existing = db.scalar(
                select(OntologyExternalIdentifier).where(
                    OntologyExternalIdentifier.kb_id == kb_id,
                    OntologyExternalIdentifier.owner_wallet_address == wallet_address,
                    OntologyExternalIdentifier.namespace == normalized_namespace,
                    OntologyExternalIdentifier.value == normalized_value,
                )
            )
            if existing is not None:
                if existing.object_id != object_id:
                    raise OntologyConflictError("external identifier is already assigned to another object") from exc
                if existing.evidence_id == evidence_id:
                    return existing
                raise OntologyConflictError(
                    "external identifier is already registered with different evidence"
                ) from exc
            raise OntologyConflictError("external identifier could not be registered") from exc
        db.refresh(record)
        return record

    def review_identity(
        self, db: Session, wallet_address: str, kb_id: int, object_id: str, *, status: str, rationale: str,
        evidence_id: int,
    ) -> OntologyIdentityReview:
        self._require_kb(db, kb_id, wallet_address)
        record = self._get_object(db, kb_id, wallet_address, object_id, lock=True)
        self._get_evidence(db, kb_id, wallet_address, evidence_id)
        if self._open_conflicts(db, kb_id, wallet_address, object_id):
            raise OntologyInvalidOperation("identity status is governed by unresolved identifier conflicts")
        normalized_rationale = rationale.strip()
        if not normalized_rationale:
            raise OntologyInvalidOperation("review rationale is required")
        existing = db.scalar(
            select(OntologyIdentityReview).where(
                OntologyIdentityReview.object_id == object_id,
                OntologyIdentityReview.kb_id == kb_id,
                OntologyIdentityReview.owner_wallet_address == wallet_address,
                OntologyIdentityReview.status == status,
                OntologyIdentityReview.rationale == normalized_rationale,
                OntologyIdentityReview.evidence_id == evidence_id,
                OntologyIdentityReview.reviewed_by == wallet_address,
            )
        )
        if existing is not None:
            return existing
        review = OntologyIdentityReview(
            object_id=object_id,
            kb_id=kb_id,
            owner_wallet_address=wallet_address,
            status=status,
            rationale=normalized_rationale,
            evidence_id=evidence_id,
            reviewed_by=wallet_address,
        )
        record.identity_status = status
        db.add(review)
        self._commit(db)
        db.refresh(review)
        return review

    def confirm_crosswalk(
        self, db: Session, wallet_address: str, kb_id: int, object_id: str, *, namespace: str,
        source_value: str, authority: str, canonical_namespace: str, canonical_value: str, evidence_id: int,
    ) -> dict:
        kb = db.scalar(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.owner_wallet_address == wallet_address,
            )
            .with_for_update()
        )
        if kb is None:
            raise OntologyNotFound("knowledge base not found")
        record = self._get_object(db, kb_id, wallet_address, object_id, lock=True)
        self._get_evidence(db, kb_id, wallet_address, evidence_id)
        if self._open_conflicts(db, kb_id, wallet_address, object_id):
            raise OntologyInvalidOperation("cannot confirm identity with unresolved identifier conflicts")
        normalized = {
            "namespace": namespace.strip(),
            "source_value": source_value.strip(),
            "authority": authority.strip(),
            "canonical_namespace": canonical_namespace.strip(),
            "canonical_value": canonical_value.strip(),
        }
        if any(not value for value in normalized.values()):
            raise OntologyInvalidOperation("crosswalk fields are required")
        source_identifier = db.scalar(
            select(OntologyExternalIdentifier).where(
                OntologyExternalIdentifier.object_id == object_id,
                OntologyExternalIdentifier.kb_id == kb_id,
                OntologyExternalIdentifier.owner_wallet_address == wallet_address,
                OntologyExternalIdentifier.namespace == normalized["namespace"],
                OntologyExternalIdentifier.value == normalized["source_value"],
            )
        )
        if source_identifier is None:
            raise OntologyInvalidOperation("source identifier must be registered to this object")
        existing_source = db.scalar(
            select(OntologyCrosswalk).where(
                OntologyCrosswalk.kb_id == kb_id,
                OntologyCrosswalk.owner_wallet_address == wallet_address,
                OntologyCrosswalk.namespace == normalized["namespace"],
                OntologyCrosswalk.source_value == normalized["source_value"],
            )
        )
        if existing_source is not None:
            same_mapping = (
                existing_source.object_id == object_id
                and existing_source.authority == normalized["authority"]
                and existing_source.canonical_namespace == normalized["canonical_namespace"]
                and existing_source.canonical_value == normalized["canonical_value"]
                and existing_source.evidence_id == evidence_id
            )
            if same_mapping:
                return {"crosswalk": existing_source, "object": self._serialize_object(db, record)}
            raise OntologyConflictError("source identifier already has a different crosswalk")
        existing_canonical = db.scalar(
            select(OntologyCrosswalk).where(
                OntologyCrosswalk.kb_id == kb_id,
                OntologyCrosswalk.owner_wallet_address == wallet_address,
                OntologyCrosswalk.canonical_namespace == normalized["canonical_namespace"],
                OntologyCrosswalk.canonical_value == normalized["canonical_value"],
                OntologyCrosswalk.object_id != object_id,
            )
        )
        if existing_canonical is not None:
            raise OntologyConflictError("canonical identifier is already assigned to another object")
        crosswalk = OntologyCrosswalk(
            object_id=object_id,
            kb_id=kb_id,
            owner_wallet_address=wallet_address,
            namespace=normalized["namespace"],
            source_value=normalized["source_value"],
            authority=normalized["authority"],
            canonical_namespace=normalized["canonical_namespace"],
            canonical_value=normalized["canonical_value"],
            evidence_id=evidence_id,
            created_by=wallet_address,
        )
        record.identity_status = "confirmed"
        db.add(crosswalk)
        db.add(
            OntologyIdentityReview(
                object_id=object_id,
                kb_id=kb_id,
                owner_wallet_address=wallet_address,
                status="confirmed",
                rationale=f"Confirmed by authoritative crosswalk: {normalized['authority']}.",
                evidence_id=evidence_id,
                reviewed_by=wallet_address,
            )
        )
        try:
            self._commit(db)
        except IntegrityError as exc:
            existing_source = db.scalar(
                select(OntologyCrosswalk).where(
                    OntologyCrosswalk.kb_id == kb_id,
                    OntologyCrosswalk.owner_wallet_address == wallet_address,
                    OntologyCrosswalk.namespace == normalized["namespace"],
                    OntologyCrosswalk.source_value == normalized["source_value"],
                )
            )
            if existing_source is not None:
                raise OntologyConflictError("source identifier already has a different crosswalk") from exc
            raise OntologyConflictError("canonical identifier is already mapped to another object") from exc
        db.refresh(crosswalk)
        db.refresh(record)
        return {"crosswalk": crosswalk, "object": self._serialize_object(db, record)}

    def report_conflict(
        self, db: Session, wallet_address: str, kb_id: int, claimant_object_id: str, *, namespace: str,
        value: str, evidence_id: int,
    ) -> dict:
        self._require_kb(db, kb_id, wallet_address)
        self._get_evidence(db, kb_id, wallet_address, evidence_id)
        normalized_namespace, normalized_value = namespace.strip(), value.strip()
        if not normalized_namespace or not normalized_value:
            raise OntologyInvalidOperation("identifier namespace and value are required")
        identifier = db.scalar(
            select(OntologyExternalIdentifier).where(
                OntologyExternalIdentifier.kb_id == kb_id,
                OntologyExternalIdentifier.owner_wallet_address == wallet_address,
                OntologyExternalIdentifier.namespace == normalized_namespace,
                OntologyExternalIdentifier.value == normalized_value,
            )
        )
        if identifier is None:
            raise OntologyInvalidOperation("conflicting identifier must already belong to an object")
        existing_object_id = identifier.object_id
        if existing_object_id == claimant_object_id:
            raise OntologyInvalidOperation("an object cannot conflict with its own identifier")
        object_ids = sorted((existing_object_id, claimant_object_id))
        locked_objects = list(
            db.scalars(
                select(OntologyObject)
                .where(
                    OntologyObject.kb_id == kb_id,
                    OntologyObject.owner_wallet_address == wallet_address,
                    OntologyObject.id.in_(object_ids),
                )
                .order_by(OntologyObject.id)
                .with_for_update()
            ).all()
        )
        if len(locked_objects) != 2:
            raise OntologyNotFound("ontology object not found")
        existing_object = next(item for item in locked_objects if item.id == existing_object_id)
        claimant_object = next(item for item in locked_objects if item.id == claimant_object_id)
        conflict = db.scalar(
            select(OntologyIdentifierConflict).where(
                OntologyIdentifierConflict.kb_id == kb_id,
                OntologyIdentifierConflict.owner_wallet_address == wallet_address,
                OntologyIdentifierConflict.existing_object_id == existing_object_id,
                OntologyIdentifierConflict.claimant_object_id == claimant_object_id,
                OntologyIdentifierConflict.namespace == normalized_namespace,
                OntologyIdentifierConflict.value == normalized_value,
            )
        )
        if conflict is not None and conflict.status != "open":
            resolution = db.scalar(
                select(OntologyConflictResolution).where(
                    OntologyConflictResolution.conflict_id == conflict.id,
                    OntologyConflictResolution.kb_id == kb_id,
                    OntologyConflictResolution.owner_wallet_address == wallet_address,
                )
            )
            if (
                resolution is not None
                and resolution.evidence_id == evidence_id
                and resolution.adjudicated_by == wallet_address
            ):
                return self._serialize_conflict(db, conflict)
            raise OntologyConflictError("identity conflict is already resolved")
        if conflict is None:
            conflict = OntologyIdentifierConflict(
                kb_id=kb_id,
                owner_wallet_address=wallet_address,
                existing_object_id=existing_object_id,
                claimant_object_id=claimant_object_id,
                namespace=normalized_namespace,
                value=normalized_value,
                status="open",
                existing_prior_status=self._prior_status(
                    db, kb_id, wallet_address, existing_object_id, existing_object.identity_status
                ),
                claimant_prior_status=self._prior_status(
                    db, kb_id, wallet_address, claimant_object_id, claimant_object.identity_status
                ),
            )
            db.add(conflict)
            db.flush()
        duplicate_report = db.scalar(
            select(OntologyIdentifierConflictReport).where(
                OntologyIdentifierConflictReport.conflict_id == conflict.id,
                OntologyIdentifierConflictReport.kb_id == kb_id,
                OntologyIdentifierConflictReport.owner_wallet_address == wallet_address,
                OntologyIdentifierConflictReport.evidence_id == evidence_id,
                OntologyIdentifierConflictReport.reported_by == wallet_address,
            )
        )
        if duplicate_report is not None:
            return self._serialize_conflict(db, conflict)
        report = OntologyIdentifierConflictReport(
            conflict_id=conflict.id,
            kb_id=kb_id,
            owner_wallet_address=wallet_address,
            evidence_id=evidence_id,
            reported_by=wallet_address,
        )
        db.add(report)
        rationale = f"Identifier claim conflicts with object {existing_object_id}."
        for record in (existing_object, claimant_object):
            record.identity_status = "ambiguous"
            db.add(
                OntologyIdentityReview(
                    object_id=record.id,
                    kb_id=kb_id,
                    owner_wallet_address=wallet_address,
                    status="ambiguous",
                    rationale=rationale,
                    evidence_id=evidence_id,
                    reviewed_by=wallet_address,
                )
            )
        try:
            self._commit(db)
        except IntegrityError as exc:
            db.rollback()
            repeated = db.scalar(
                select(OntologyIdentifierConflict).where(
                    OntologyIdentifierConflict.kb_id == kb_id,
                    OntologyIdentifierConflict.owner_wallet_address == wallet_address,
                    OntologyIdentifierConflict.existing_object_id == existing_object_id,
                    OntologyIdentifierConflict.claimant_object_id == claimant_object_id,
                    OntologyIdentifierConflict.namespace == normalized_namespace,
                    OntologyIdentifierConflict.value == normalized_value,
                )
            )
            if repeated is not None:
                duplicate_report = db.scalar(
                    select(OntologyIdentifierConflictReport).where(
                        OntologyIdentifierConflictReport.conflict_id == repeated.id,
                        OntologyIdentifierConflictReport.evidence_id == evidence_id,
                        OntologyIdentifierConflictReport.reported_by == wallet_address,
                    )
                )
                if duplicate_report is not None:
                    return self._serialize_conflict(db, repeated)
            raise OntologyConflictError("identity conflict report could not be recorded") from exc
        return self._serialize_conflict(db, conflict)

    def list_conflicts(
        self, db: Session, wallet_address: str, kb_id: int, *, status: str | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[dict]:
        self._require_kb(db, kb_id, wallet_address)
        query = select(OntologyIdentifierConflict).where(
            OntologyIdentifierConflict.kb_id == kb_id,
            OntologyIdentifierConflict.owner_wallet_address == wallet_address,
        )
        if status is not None:
            query = query.where(OntologyIdentifierConflict.status == status)
        conflicts = db.scalars(
            query.order_by(OntologyIdentifierConflict.reported_at.desc(), OntologyIdentifierConflict.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [self._serialize_conflict(db, conflict) for conflict in conflicts]

    def get_conflict(self, db: Session, wallet_address: str, kb_id: int, conflict_id: str) -> dict:
        self._require_kb(db, kb_id, wallet_address)
        return self._serialize_conflict(db, self._get_conflict(db, kb_id, wallet_address, conflict_id))

    def adjudicate_conflict(
        self, db: Session, wallet_address: str, kb_id: int, conflict_id: str, *, decision: str,
        rationale: str, evidence_id: int,
    ) -> dict:
        self._require_kb(db, kb_id, wallet_address)
        conflict = self._get_conflict(db, kb_id, wallet_address, conflict_id, lock=True)
        self._get_evidence(db, kb_id, wallet_address, evidence_id)
        normalized_rationale = rationale.strip()
        if not normalized_rationale:
            raise OntologyInvalidOperation("adjudication rationale is required")
        if decision != "claim_rejected":
            raise OntologyInvalidOperation("unsupported adjudication decision")
        existing = db.scalar(
            select(OntologyConflictResolution).where(
                OntologyConflictResolution.conflict_id == conflict.id,
                OntologyConflictResolution.kb_id == kb_id,
                OntologyConflictResolution.owner_wallet_address == wallet_address,
            )
        )
        if existing is not None:
            if (
                existing.decision == decision
                and existing.rationale == normalized_rationale
                and existing.evidence_id == evidence_id
                and existing.adjudicated_by == wallet_address
            ):
                return self._serialize_conflict(db, conflict)
            raise OntologyConflictError("identity conflict is already resolved")
        if conflict.status != "open":
            raise OntologyConflictError("identity conflict is already resolved")
        resolution = OntologyConflictResolution(
            conflict_id=conflict.id,
            kb_id=kb_id,
            owner_wallet_address=wallet_address,
            decision=decision,
            rationale=normalized_rationale,
            evidence_id=evidence_id,
            adjudicated_by=wallet_address,
        )
        conflict.status = "claim_rejected"
        db.add(resolution)
        object_ids = sorted((conflict.existing_object_id, conflict.claimant_object_id))
        locked_objects = list(
            db.scalars(
                select(OntologyObject)
                .where(
                    OntologyObject.kb_id == kb_id,
                    OntologyObject.owner_wallet_address == wallet_address,
                    OntologyObject.id.in_(object_ids),
                )
                .order_by(OntologyObject.id)
                .with_for_update()
            ).all()
        )
        if len(locked_objects) != 2:
            raise OntologyNotFound("ontology object not found")
        objects_by_id = {record.id: record for record in locked_objects}
        for object_id, prior_status in (
            (conflict.existing_object_id, conflict.existing_prior_status),
            (conflict.claimant_object_id, conflict.claimant_prior_status),
        ):
            record = objects_by_id[object_id]
            record.identity_status = self._prior_status(
                db, kb_id, wallet_address, object_id, prior_status
            )
            db.add(
                OntologyIdentityReview(
                    object_id=object_id,
                    kb_id=kb_id,
                    owner_wallet_address=wallet_address,
                    status=record.identity_status,
                    rationale=f"Adjudication rejected the competing identifier claim: {normalized_rationale}",
                    evidence_id=evidence_id,
                    reviewed_by=wallet_address,
                )
            )
        self._commit(db)
        return self._serialize_conflict(db, conflict)
