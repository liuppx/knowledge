from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from knowledge.api.deps import get_current_wallet
from knowledge.core.settings import get_settings
from knowledge.db.session import get_db
from knowledge.schemas.ontology import (
    OntologyConflictAdjudicate,
    OntologyConflictRead,
    OntologyConflictReportCreate,
    OntologyCrosswalkCreate,
    OntologyCrosswalkRead,
    OntologyEvidenceCreate,
    OntologyEvidenceRead,
    OntologyIdentifierCreate,
    OntologyIdentifierRead,
    OntologyObjectCreate,
    OntologyObjectRead,
    OntologyReviewCreate,
    OntologyReviewRead,
)
from knowledge.services.ontology import OntologyError, OntologyService


settings = get_settings()


def require_ontology_enabled() -> None:
    if not settings.ontology_identity_enabled:
        raise HTTPException(status_code=404, detail="ontology identity endpoints are disabled")


router = APIRouter(
    prefix="/kbs/{kb_id}/ontology",
    tags=["ontology"],
    dependencies=[Depends(require_ontology_enabled)],
)
ontology_service = OntologyService()


def _raise_http_error(exc: OntologyError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/evidence", response_model=OntologyEvidenceRead, status_code=status.HTTP_201_CREATED)
def create_evidence(
    kb_id: int,
    payload: OntologyEvidenceCreate,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyEvidenceRead:
    try:
        return ontology_service.create_evidence(db, wallet_address, kb_id, **payload.model_dump())
    except OntologyError as exc:
        _raise_http_error(exc)


@router.get("/evidence/{evidence_id}", response_model=OntologyEvidenceRead)
def get_evidence(
    kb_id: int,
    evidence_id: int,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyEvidenceRead:
    try:
        ontology_service._require_kb(db, kb_id, wallet_address)
        return ontology_service._get_evidence(db, kb_id, wallet_address, evidence_id)
    except OntologyError as exc:
        _raise_http_error(exc)


@router.post("/objects", response_model=OntologyObjectRead, status_code=status.HTTP_201_CREATED)
def create_object(
    kb_id: int,
    payload: OntologyObjectCreate,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyObjectRead:
    try:
        return ontology_service.create_object(db, wallet_address, kb_id, **payload.model_dump())
    except OntologyError as exc:
        _raise_http_error(exc)


@router.get("/objects", response_model=list[OntologyObjectRead])
def list_objects(
    kb_id: int,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> list[OntologyObjectRead]:
    try:
        return ontology_service.list_objects(db, wallet_address, kb_id, limit=limit, offset=offset)
    except OntologyError as exc:
        _raise_http_error(exc)


@router.get("/objects/{object_id}", response_model=OntologyObjectRead)
def get_object(
    kb_id: int,
    object_id: str,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyObjectRead:
    try:
        return ontology_service.get_object(db, wallet_address, kb_id, object_id)
    except OntologyError as exc:
        _raise_http_error(exc)


@router.post(
    "/objects/{object_id}/identifiers",
    response_model=OntologyIdentifierRead,
    status_code=status.HTTP_201_CREATED,
)
def register_identifier(
    kb_id: int,
    object_id: str,
    payload: OntologyIdentifierCreate,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyIdentifierRead:
    try:
        return ontology_service.register_identifier(db, wallet_address, kb_id, object_id, **payload.model_dump())
    except OntologyError as exc:
        _raise_http_error(exc)


@router.post("/objects/{object_id}/reviews", response_model=OntologyReviewRead, status_code=status.HTTP_201_CREATED)
def review_identity(
    kb_id: int,
    object_id: str,
    payload: OntologyReviewCreate,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyReviewRead:
    try:
        return ontology_service.review_identity(db, wallet_address, kb_id, object_id, **payload.model_dump())
    except OntologyError as exc:
        _raise_http_error(exc)


@router.post(
    "/objects/{object_id}/crosswalks",
    response_model=OntologyCrosswalkRead,
    status_code=status.HTTP_201_CREATED,
)
def confirm_crosswalk(
    kb_id: int,
    object_id: str,
    payload: OntologyCrosswalkCreate,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyCrosswalkRead:
    try:
        result = ontology_service.confirm_crosswalk(db, wallet_address, kb_id, object_id, **payload.model_dump())
        return result["crosswalk"]
    except OntologyError as exc:
        _raise_http_error(exc)


@router.post(
    "/objects/{claimant_object_id}/conflicts",
    response_model=OntologyConflictRead,
    status_code=status.HTTP_201_CREATED,
)
def report_identifier_conflict(
    kb_id: int,
    claimant_object_id: str,
    payload: OntologyConflictReportCreate,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyConflictRead:
    try:
        return ontology_service.report_conflict(
            db, wallet_address, kb_id, claimant_object_id, **payload.model_dump()
        )
    except OntologyError as exc:
        _raise_http_error(exc)


@router.get("/conflicts", response_model=list[OntologyConflictRead])
def list_conflicts(
    kb_id: int,
    conflict_status: Literal["open", "claim_rejected"] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> list[OntologyConflictRead]:
    try:
        return ontology_service.list_conflicts(
            db, wallet_address, kb_id, status=conflict_status, limit=limit, offset=offset
        )
    except OntologyError as exc:
        _raise_http_error(exc)


@router.get("/conflicts/{conflict_id}", response_model=OntologyConflictRead)
def get_conflict(
    kb_id: int,
    conflict_id: str,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyConflictRead:
    try:
        return ontology_service.get_conflict(db, wallet_address, kb_id, conflict_id)
    except OntologyError as exc:
        _raise_http_error(exc)


@router.post(
    "/conflicts/{conflict_id}/adjudications",
    response_model=OntologyConflictRead,
)
def adjudicate_conflict(
    kb_id: int,
    conflict_id: str,
    payload: OntologyConflictAdjudicate,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> OntologyConflictRead:
    try:
        return ontology_service.adjudicate_conflict(
            db, wallet_address, kb_id, conflict_id, **payload.model_dump()
        )
    except OntologyError as exc:
        _raise_http_error(exc)
