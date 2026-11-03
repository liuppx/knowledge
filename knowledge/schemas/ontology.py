from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


IdentityStatusValue = Literal["candidate", "confirmed", "ambiguous", "insufficient_evidence"]
ReviewStatusValue = Literal["candidate", "ambiguous", "insufficient_evidence"]
ObjectTypeValue = Literal["contract", "product", "organization"]


class OntologyEvidenceCreate(BaseModel):
    uri: str = Field(min_length=1, max_length=2048)
    source_version: str = Field(min_length=1, max_length=255)
    locator: str = ""
    checksum: str = Field(default="", max_length=128)


class OntologyEvidenceRead(OntologyEvidenceCreate):
    id: int
    created_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyObjectCreate(BaseModel):
    object_type: ObjectTypeValue
    label: str = Field(min_length=1, max_length=512)
    evidence_id: int = Field(gt=0)


class OntologyIdentifierCreate(BaseModel):
    namespace: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=1024)
    evidence_id: int = Field(gt=0)


class OntologyReviewCreate(BaseModel):
    status: ReviewStatusValue
    rationale: str = Field(min_length=1)
    evidence_id: int = Field(gt=0)


class OntologyCrosswalkCreate(BaseModel):
    namespace: str = Field(min_length=1, max_length=255)
    source_value: str = Field(min_length=1, max_length=1024)
    authority: str = Field(min_length=1, max_length=255)
    canonical_namespace: str = Field(min_length=1, max_length=255)
    canonical_value: str = Field(min_length=1, max_length=1024)
    evidence_id: int = Field(gt=0)


class OntologyConflictReportCreate(BaseModel):
    namespace: str = Field(min_length=1, max_length=255)
    value: str = Field(min_length=1, max_length=1024)
    evidence_id: int = Field(gt=0)


class OntologyConflictAdjudicate(BaseModel):
    decision: Literal["claim_rejected"] = "claim_rejected"
    rationale: str = Field(min_length=1)
    evidence_id: int = Field(gt=0)


class OntologyIdentifierRead(BaseModel):
    id: int
    object_id: str
    namespace: str
    value: str
    evidence_id: int
    registered_by: str
    registered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyReviewRead(BaseModel):
    id: int
    status: IdentityStatusValue
    rationale: str
    evidence_id: int
    reviewed_by: str
    reviewed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyCrosswalkRead(BaseModel):
    id: int
    namespace: str
    source_value: str
    authority: str
    canonical_namespace: str
    canonical_value: str
    evidence_id: int
    created_by: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyObjectRead(BaseModel):
    id: str
    kb_id: int
    object_type: ObjectTypeValue
    label: str
    identity_status: IdentityStatusValue
    created_by: str
    created_at: datetime
    updated_at: datetime
    identifiers: list[OntologyIdentifierRead] = Field(default_factory=list)
    reviews: list[OntologyReviewRead] = Field(default_factory=list)
    crosswalks: list[OntologyCrosswalkRead] = Field(default_factory=list)


class OntologyConflictResolutionRead(BaseModel):
    decision: Literal["claim_rejected"]
    rationale: str
    evidence_id: int
    adjudicated_by: str
    adjudicated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyConflictReportRead(BaseModel):
    id: int
    evidence_id: int
    reported_by: str
    reported_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OntologyConflictRead(BaseModel):
    id: str
    kb_id: int
    existing_object_id: str
    claimant_object_id: str
    namespace: str
    value: str
    status: Literal["open", "claim_rejected"]
    reported_at: datetime
    reports: list[OntologyConflictReportRead] = Field(default_factory=list)
    resolution: OntologyConflictResolutionRead | None = None
