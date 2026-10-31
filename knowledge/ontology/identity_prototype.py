"""In-memory identity and crosswalk prototype for controlled evaluation.

This module is deliberately not wired to the production API or database. It
exists to test the identity-review workflow with public or synthetic records.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping
from uuid import uuid4


class ObjectType(str, Enum):
    CONTRACT = "contract"
    PRODUCT = "product"
    ORGANIZATION = "organization"


class IdentityStatus(str, Enum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class IdentityRole(str, Enum):
    CONTRIBUTOR = "contributor"
    REVIEWER = "reviewer"
    ADJUDICATOR = "adjudicator"


class IdentityPermission(str, Enum):
    CREATE_OBJECT = "create_object"
    REGISTER_IDENTIFIER = "register_identifier"
    REVIEW_IDENTITY = "review_identity"
    CONFIRM_CROSSWALK = "confirm_crosswalk"
    REPORT_CONFLICT = "report_conflict"
    REJECT_IDENTIFIER_CLAIM = "reject_identifier_claim"


ROLE_PERMISSIONS: Mapping[IdentityRole, frozenset[IdentityPermission]] = {
    IdentityRole.CONTRIBUTOR: frozenset(
        {IdentityPermission.CREATE_OBJECT, IdentityPermission.REGISTER_IDENTIFIER}
    ),
    IdentityRole.REVIEWER: frozenset(
        {
            IdentityPermission.CREATE_OBJECT,
            IdentityPermission.REGISTER_IDENTIFIER,
            IdentityPermission.REVIEW_IDENTITY,
            IdentityPermission.CONFIRM_CROSSWALK,
            IdentityPermission.REPORT_CONFLICT,
        }
    ),
    IdentityRole.ADJUDICATOR: frozenset({IdentityPermission.REJECT_IDENTIFIER_CLAIM}),
}


@dataclass(frozen=True)
class EvidenceReference:
    uri: str
    source_version: str
    locator: str = ""
    checksum: str = ""

    def __post_init__(self) -> None:
        if not self.uri.strip():
            raise ValueError("evidence uri is required")
        if not self.source_version.strip():
            raise ValueError("evidence source_version is required")


@dataclass(frozen=True)
class ExternalIdentifier:
    namespace: str
    value: str
    evidence: EvidenceReference
    registered_by: str
    registered_at: datetime

    def __post_init__(self) -> None:
        if not self.namespace.strip():
            raise ValueError("identifier namespace is required")
        if not self.value.strip():
            raise ValueError("identifier value is required")
        if not self.registered_by.strip():
            raise ValueError("identifier registered_by is required")


@dataclass(frozen=True)
class Crosswalk:
    namespace: str
    source_value: str
    authority: str
    canonical_namespace: str
    canonical_value: str
    evidence: EvidenceReference
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class IdentityReview:
    status: IdentityStatus
    rationale: str
    evidence: EvidenceReference
    reviewed_by: str
    reviewed_at: datetime


@dataclass(frozen=True)
class IdentityConflictResolution:
    decision: str
    rationale: str
    evidence: EvidenceReference
    adjudicated_by: str
    adjudicated_at: datetime


@dataclass(frozen=True)
class IdentityConflict:
    id: str
    existing_object_id: str
    claimant_object_id: str
    namespace: str
    value: str
    status: str
    existing_prior_status: IdentityStatus
    claimant_prior_status: IdentityStatus
    evidence: tuple[EvidenceReference, ...]
    reported_by: tuple[str, ...]
    reported_at: datetime
    resolution: IdentityConflictResolution | None = None


@dataclass
class DomainObject:
    id: str
    object_type: ObjectType
    label: str
    identity_status: IdentityStatus
    identifiers: list[ExternalIdentifier] = field(default_factory=list)
    crosswalks: list[Crosswalk] = field(default_factory=list)
    reviews: list[IdentityReview] = field(default_factory=list)


class IdentityPrototype:
    """Small in-memory service with an explicit, non-production role boundary."""

    def __init__(self, actor_roles: Mapping[str, IdentityRole | str] | None = None) -> None:
        self._objects: dict[str, DomainObject] = {}
        self._identifier_owners: dict[tuple[str, str], str] = {}
        self._conflicts: dict[str, IdentityConflict] = {}
        self._conflict_keys: dict[tuple[str, str, str, str], str] = {}
        self._actor_roles: dict[str, IdentityRole] = {}
        for actor_id, role in (actor_roles or {}).items():
            self.register_actor(actor_id, role)

    def register_actor(self, actor_id: str, role: IdentityRole | str) -> None:
        normalized_actor_id = actor_id.strip()
        if not normalized_actor_id:
            raise ValueError("actor_id is required")
        parsed_role = IdentityRole(role)
        previous_role = self._actor_roles.get(normalized_actor_id)
        if previous_role is not None and previous_role is not parsed_role:
            raise ValueError("actor is already registered with another role")
        self._actor_roles[normalized_actor_id] = parsed_role

    def _authorize(self, actor_id: str, permission: IdentityPermission) -> str:
        normalized_actor_id = actor_id.strip()
        role = self._actor_roles.get(normalized_actor_id)
        if role is None or permission not in ROLE_PERMISSIONS[role]:
            raise PermissionError(
                f"actor {(normalized_actor_id or '<empty>')!r} is not authorized for {permission.value}"
            )
        return normalized_actor_id

    def create_object(
        self,
        object_type: ObjectType | str,
        label: str,
        *,
        created_by: str,
        evidence: EvidenceReference,
    ) -> DomainObject:
        parsed_type = ObjectType(object_type)
        normalized_created_by = self._authorize(created_by, IdentityPermission.CREATE_OBJECT)
        self._require_evidence(evidence)
        normalized_label = label.strip()
        if not normalized_label:
            raise ValueError("object label is required")
        record = DomainObject(
            id=str(uuid4()),
            object_type=parsed_type,
            label=normalized_label,
            identity_status=IdentityStatus.CANDIDATE,
            reviews=[
                IdentityReview(
                    status=IdentityStatus.CANDIDATE,
                    rationale="Object created for identity review.",
                    evidence=evidence,
                    reviewed_by=normalized_created_by,
                    reviewed_at=self._now(),
                )
            ],
        )
        self._objects[record.id] = record
        return deepcopy(record)

    def get_object(self, object_id: str) -> DomainObject:
        return deepcopy(self._get_object(object_id))

    def _get_object(self, object_id: str) -> DomainObject:
        try:
            return self._objects[object_id]
        except KeyError as exc:
            raise LookupError("object not found") from exc

    def list_objects(self) -> list[DomainObject]:
        return deepcopy(sorted(self._objects.values(), key=lambda record: record.id))

    def list_conflicts(self) -> list[IdentityConflict]:
        return sorted(self._conflicts.values(), key=lambda conflict: (conflict.reported_at, conflict.id))

    def _open_conflicts_for(self, object_id: str) -> list[IdentityConflict]:
        return [
            conflict
            for conflict in self.list_conflicts()
            if conflict.status == "open"
            and object_id in (conflict.existing_object_id, conflict.claimant_object_id)
        ]

    def _status_before_open_conflicts(self, object_id: str) -> IdentityStatus:
        conflicts = self._open_conflicts_for(object_id)
        if not conflicts:
            return self._get_object(object_id).identity_status
        conflict = conflicts[0]
        if conflict.existing_object_id == object_id:
            return conflict.existing_prior_status
        return conflict.claimant_prior_status

    def add_identifier(
        self,
        object_id: str,
        namespace: str,
        value: str,
        *,
        evidence: EvidenceReference,
        registered_by: str,
    ) -> ExternalIdentifier:
        record = self._get_object(object_id)
        normalized_registered_by = self._authorize(
            registered_by, IdentityPermission.REGISTER_IDENTIFIER
        )
        self._require_evidence(evidence)
        normalized_namespace = namespace.strip()
        normalized_value = value.strip()
        identifier_key = (normalized_namespace, normalized_value)
        existing_identifier = next(
            (
                item
                for item in record.identifiers
                if (item.namespace, item.value) == identifier_key
            ),
            None,
        )
        if existing_identifier is not None:
            return existing_identifier
        identifier = ExternalIdentifier(
            normalized_namespace,
            normalized_value,
            evidence,
            normalized_registered_by,
            self._now(),
        )
        key = (identifier.namespace, identifier.value)
        owner_id = self._identifier_owners.get(key)
        if owner_id is not None and owner_id != object_id:
            raise ValueError("external identifier is already assigned to another object")
        if identifier not in record.identifiers:
            record.identifiers.append(identifier)
            self._identifier_owners[key] = object_id
        return identifier

    def record_identifier_conflict(
        self,
        claimant_object_id: str,
        namespace: str,
        value: str,
        *,
        evidence: EvidenceReference,
        reported_by: str,
    ) -> IdentityConflict:
        claimant = self._get_object(claimant_object_id)
        normalized_reported_by = self._authorize(reported_by, IdentityPermission.REPORT_CONFLICT)
        self._require_evidence(evidence)
        key = (namespace.strip(), value.strip())
        existing_object_id = self._identifier_owners.get(key)
        if existing_object_id is None:
            raise ValueError("conflicting identifier must already belong to an object")
        if existing_object_id == claimant_object_id:
            raise ValueError("an object cannot conflict with its own identifier")

        conflict_key = (*key, existing_object_id, claimant_object_id)
        previous_id = self._conflict_keys.get(conflict_key)
        if previous_id is not None:
            previous = self._conflicts[previous_id]
            if previous.resolution is not None:
                if evidence in previous.evidence and normalized_reported_by in previous.reported_by:
                    return previous
                raise ValueError("identity conflict is already resolved")
            add_evidence = evidence not in previous.evidence
            add_reporter = normalized_reported_by not in previous.reported_by
            if not add_evidence and not add_reporter:
                return previous
            updated = replace(
                previous,
                evidence=previous.evidence + ((evidence,) if add_evidence else ()),
                reported_by=previous.reported_by + ((normalized_reported_by,) if add_reporter else ()),
            )
            self._conflicts[previous_id] = updated
            if add_evidence or add_reporter:
                rationale = f"Identifier claim conflicts with object {existing_object_id}."
                for record in (self._get_object(existing_object_id), self._get_object(claimant_object_id)):
                    record.identity_status = IdentityStatus.AMBIGUOUS
                    record.reviews.append(
                        IdentityReview(
                            status=IdentityStatus.AMBIGUOUS,
                            rationale=rationale,
                            evidence=evidence,
                            reviewed_by=normalized_reported_by,
                            reviewed_at=self._now(),
                        )
                    )
            return updated

        existing = self._get_object(existing_object_id)
        conflict = IdentityConflict(
            id=str(uuid4()),
            existing_object_id=existing_object_id,
            claimant_object_id=claimant_object_id,
            namespace=key[0],
            value=key[1],
            status="open",
            existing_prior_status=self._status_before_open_conflicts(existing_object_id),
            claimant_prior_status=self._status_before_open_conflicts(claimant_object_id),
            evidence=(evidence,),
            reported_by=(normalized_reported_by,),
            reported_at=self._now(),
        )
        rationale = f"Identifier claim conflicts with object {existing_object_id}."
        for record in (existing, claimant):
            record.identity_status = IdentityStatus.AMBIGUOUS
            record.reviews.append(
                IdentityReview(
                    status=IdentityStatus.AMBIGUOUS,
                    rationale=rationale,
                    evidence=evidence,
                    reviewed_by=normalized_reported_by,
                    reviewed_at=conflict.reported_at,
                )
            )
        self._conflicts[conflict.id] = conflict
        self._conflict_keys[conflict_key] = conflict.id
        return conflict

    def reject_identifier_claim(
        self,
        conflict_id: str,
        *,
        rationale: str,
        evidence: EvidenceReference,
        adjudicated_by: str,
    ) -> IdentityConflict:
        conflict = self._conflicts.get(conflict_id)
        if conflict is None:
            raise LookupError("identity conflict not found")
        normalized_adjudicated_by = self._authorize(
            adjudicated_by, IdentityPermission.REJECT_IDENTIFIER_CLAIM
        )
        self._require_evidence(evidence)
        if not rationale.strip():
            raise ValueError("adjudication rationale is required")
        if conflict.resolution is not None:
            resolution = conflict.resolution
            if (
                resolution.decision == "claim_rejected"
                and resolution.rationale == rationale.strip()
                and resolution.evidence == evidence
                and resolution.adjudicated_by == normalized_adjudicated_by
            ):
                return conflict
            raise ValueError("identity conflict is already resolved")

        resolved_at = self._now()
        resolution = IdentityConflictResolution(
            decision="claim_rejected",
            rationale=rationale.strip(),
            evidence=evidence,
            adjudicated_by=normalized_adjudicated_by,
            adjudicated_at=resolved_at,
        )
        updated = replace(
            conflict,
            status="claim_rejected",
            evidence=conflict.evidence + ((evidence,) if evidence not in conflict.evidence else ()),
            reported_by=(
                conflict.reported_by
                if normalized_adjudicated_by in conflict.reported_by
                else conflict.reported_by + (normalized_adjudicated_by,)
            ),
            resolution=resolution,
        )
        self._conflicts[conflict_id] = updated

        rationale_text = f"Adjudication rejected the competing identifier claim: {rationale.strip()}"
        for object_id, prior_status in (
            (conflict.existing_object_id, conflict.existing_prior_status),
            (conflict.claimant_object_id, conflict.claimant_prior_status),
        ):
            record = self._get_object(object_id)
            record.identity_status = (
                IdentityStatus.AMBIGUOUS
                if self._open_conflicts_for(object_id)
                else prior_status
            )
            record.reviews.append(
                IdentityReview(
                    status=record.identity_status,
                    rationale=rationale_text,
                    evidence=evidence,
                    reviewed_by=normalized_adjudicated_by,
                    reviewed_at=resolved_at,
                )
            )
        return updated

    def review_identity(
        self,
        object_id: str,
        status: IdentityStatus | str,
        *,
        rationale: str,
        evidence: EvidenceReference,
        reviewed_by: str,
    ) -> IdentityReview:
        record = self._get_object(object_id)
        normalized_reviewed_by = self._authorize(reviewed_by, IdentityPermission.REVIEW_IDENTITY)
        self._require_evidence(evidence)
        parsed_status = IdentityStatus(status)
        if parsed_status is IdentityStatus.CONFIRMED:
            raise ValueError("confirmed identity requires an authoritative crosswalk")
        if self._open_conflicts_for(object_id):
            raise ValueError("identity status is governed by unresolved identifier conflicts")
        if not rationale.strip():
            raise ValueError("review rationale is required")
        review = IdentityReview(
            status=parsed_status,
            rationale=rationale.strip(),
            evidence=evidence,
            reviewed_by=normalized_reviewed_by,
            reviewed_at=self._now(),
        )
        record.identity_status = parsed_status
        record.reviews.append(review)
        return review

    def confirm_crosswalk(
        self,
        object_id: str,
        *,
        namespace: str,
        source_value: str,
        authority: str,
        canonical_namespace: str,
        canonical_value: str,
        evidence: EvidenceReference,
        confirmed_by: str,
    ) -> Crosswalk:
        record = self._get_object(object_id)
        normalized_confirmed_by = self._authorize(
            confirmed_by, IdentityPermission.CONFIRM_CROSSWALK
        )
        self._require_evidence(evidence)
        if self._open_conflicts_for(object_id):
            raise ValueError("cannot confirm identity with unresolved identifier conflicts")
        source_key = (namespace.strip(), source_value.strip())
        if self._identifier_owners.get(source_key) != object_id:
            raise ValueError("source identifier must be registered to this object")
        fields = {
            "authority": authority,
            "canonical_namespace": canonical_namespace,
            "canonical_value": canonical_value,
            "confirmed_by": normalized_confirmed_by,
        }
        missing = [name for name, value in fields.items() if not value.strip()]
        if missing:
            raise ValueError(f"crosswalk requires: {', '.join(missing)}")
        crosswalk = Crosswalk(
            namespace=source_key[0],
            source_value=source_key[1],
            authority=authority.strip(),
            canonical_namespace=canonical_namespace.strip(),
            canonical_value=canonical_value.strip(),
            evidence=evidence,
            created_by=normalized_confirmed_by,
            created_at=self._now(),
        )
        identity_key = (crosswalk.canonical_namespace, crosswalk.canonical_value)
        owner_id = self._identifier_owners.get(identity_key)
        if owner_id is not None and owner_id != object_id:
            raise ValueError("canonical identifier is already assigned to another object")
        if crosswalk not in record.crosswalks:
            record.crosswalks.append(crosswalk)
            self._identifier_owners[identity_key] = object_id
        record.identity_status = IdentityStatus.CONFIRMED
        record.reviews.append(
            IdentityReview(
                status=IdentityStatus.CONFIRMED,
                rationale=f"Confirmed by authoritative crosswalk: {authority.strip()}.",
                evidence=evidence,
                reviewed_by=normalized_confirmed_by,
                reviewed_at=crosswalk.created_at,
            )
        )
        return crosswalk

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _require_evidence(evidence: EvidenceReference) -> None:
        if not isinstance(evidence, EvidenceReference):
            raise ValueError("evidence reference is required")
