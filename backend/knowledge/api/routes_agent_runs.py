from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from knowledge.api.deps import get_current_wallet
from knowledge.db.session import get_db
from knowledge.models import AgentRun
from knowledge.schemas.agent_runs import (
    AgentRunArtifactRead,
    AgentRunContextUpdateRequest,
    AgentRunCreateRequest,
    AgentRunFinishRequest,
    AgentRunRead,
)
from knowledge.services.agent_runs import AgentRunService
from knowledge.services.agent_run_artifacts import AgentRunArtifactService
from knowledge.services.agent_run_manifests import AgentRunManifestService
from knowledge.services.service_principals import ServicePrincipalService


router = APIRouter(tags=["agent_runs"])
agent_run_service = AgentRunService()
principal_service = ServicePrincipalService()
manifest_service = AgentRunManifestService()
artifact_service = AgentRunArtifactService(run_service=agent_run_service)


def sync_manifest(db: Session, run):
    return manifest_service.sync(db, run)


def parse_json_object(value: str, label: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{label} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail=f"{label} must be a JSON object")
    return parsed


def get_service_principal(
    x_service_api_key: str = Header(alias="X-Service-Api-Key"),
    db: Session = Depends(get_db),
):
    try:
        return principal_service.verify_api_key(db, x_service_api_key)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/service/runs", response_model=AgentRunRead)
def create_agent_run(
    payload: AgentRunCreateRequest,
    principal=Depends(get_service_principal),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    try:
        run = agent_run_service.create_run(
            db,
            principal,
            session_id=payload.session_id,
            external_id=payload.external_id,
            run_type=payload.run_type,
            inputs=payload.inputs,
            metadata=payload.metadata,
        )
        return sync_manifest(db, run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/service/runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(
    run_id: str,
    principal=Depends(get_service_principal),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    try:
        return agent_run_service.get_run(db, principal, run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/service/runs/{run_id}/context", response_model=AgentRunRead)
def update_agent_run_context(
    run_id: str,
    payload: AgentRunContextUpdateRequest,
    principal=Depends(get_service_principal),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    try:
        run = agent_run_service.update_context(db, principal, run_id, payload.context)
        return sync_manifest(db, run)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _finish(run_id: str, status: str, payload: AgentRunFinishRequest, principal, db: Session):
    try:
        run = agent_run_service.finish_run(
            db,
            principal,
            run_id,
            status,
            error_summary=payload.error_summary,
        )
        return sync_manifest(db, run)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/service/runs/{run_id}/complete", response_model=AgentRunRead)
def complete_agent_run(
    run_id: str,
    payload: AgentRunFinishRequest,
    principal=Depends(get_service_principal),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    return _finish(run_id, "completed", payload, principal, db)


@router.post("/service/runs/{run_id}/artifacts", response_model=AgentRunArtifactRead)
async def upload_agent_run_artifact(
    run_id: str,
    file: UploadFile = File(...),
    artifact_key: str = Form(...),
    artifact_type: str = Form("other"),
    role: str = Form("output"),
    status: str = Form("draft"),
    generated_by: str = Form("{}"),
    metadata: str = Form("{}"),
    principal=Depends(get_service_principal),
    db: Session = Depends(get_db),
) -> AgentRunArtifactRead:
    content = await file.read()
    try:
        item = artifact_service.upload(
            db,
            principal,
            run_id,
            artifact_key=artifact_key,
            artifact_type=artifact_type,
            role=role,
            status=status,
            file_name=file.filename or artifact_key,
            content_type=file.content_type or "application/octet-stream",
            content=content,
            generated_by=parse_json_object(generated_by, "generated_by"),
            metadata=parse_json_object(metadata, "metadata"),
        )
        run = agent_run_service.get_run(db, principal, run_id)
        sync_manifest(db, run)
        return item
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/service/runs/{run_id}/fail", response_model=AgentRunRead)
def fail_agent_run(
    run_id: str,
    payload: AgentRunFinishRequest,
    principal=Depends(get_service_principal),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    return _finish(run_id, "failed", payload, principal, db)


@router.post("/service/runs/{run_id}/cancel", response_model=AgentRunRead)
def cancel_agent_run(
    run_id: str,
    payload: AgentRunFinishRequest,
    principal=Depends(get_service_principal),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    return _finish(run_id, "cancelled", payload, principal, db)


@router.post("/runs/{run_id}/manifest/retry", response_model=AgentRunRead)
def retry_agent_run_manifest(
    run_id: str,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    run = db.get(AgentRun, run_id)
    if run is None or run.owner_wallet_address != wallet_address:
        raise HTTPException(status_code=404, detail="agent run not found")
    return sync_manifest(db, run)
