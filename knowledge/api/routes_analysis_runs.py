from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import json
import time
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.api.deps import get_current_wallet
from knowledge.db.session import SessionLocal, get_db
from knowledge.models import AgentRun, AgentRunArtifact, AgentRunEvent, ServicePrincipal
from knowledge.schemas.agent_runs import AgentRunArtifactRead, AgentRunEventRead, AgentRunRead
from knowledge.services.agent_run_manifests import AgentRunManifestService
from knowledge.services.agent_runs import AgentRunService
from knowledge.services.service_principals import ServicePrincipalService


router = APIRouter(prefix="/analysis-runs", tags=["analysis_runs"])
agent_run_service = AgentRunService()
manifest_service = AgentRunManifestService()
principal_service = ServicePrincipalService()


class AnalysisRunCreateRequest(BaseModel):
    warehouse_path: str = Field(min_length=1, max_length=1024)
    intent: str = Field(min_length=1, max_length=4000)
    constraints: dict = Field(default_factory=dict)


def _analysis_principal(db: Session, wallet_address: str) -> ServicePrincipal:
    principal = db.scalar(
        select(ServicePrincipal)
        .where(ServicePrincipal.owner_wallet_address == wallet_address)
        .where(ServicePrincipal.service_id == "knowledge-analysis")
    )
    if principal is not None:
        return principal
    principal, _ = principal_service.create_principal(
        db,
        wallet_address,
        service_id="knowledge-analysis",
        display_name="Knowledge analysis",
    )
    return principal


@router.post("", response_model=AgentRunRead)
def create_my_analysis_run(
    payload: AnalysisRunCreateRequest,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    try:
        run = agent_run_service.create_run(
            db,
            _analysis_principal(db, wallet_address),
            run_type="spreadsheet_analysis",
            inputs=[{"kind": "warehouse_asset", "warehousePath": payload.warehouse_path, "role": "source"}],
            metadata={"intent": payload.intent, "constraints": payload.constraints, "created_via": "analysis-runs"},
        )
        return manifest_service.sync(db, run)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[AgentRunRead])
def list_my_analysis_runs(
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> list[AgentRunRead]:
    return list(
        db.scalars(
            select(AgentRun)
            .where(AgentRun.owner_wallet_address == wallet_address)
            .where(AgentRun.run_type == "spreadsheet_analysis")
            .order_by(AgentRun.created_at.desc())
        ).all()
    )


@router.get("/{run_id}", response_model=AgentRunRead)
def get_my_analysis_run(
    run_id: str,
    wallet_address: str = Depends(get_current_wallet),
    db: Session = Depends(get_db),
) -> AgentRunRead:
    run = db.get(AgentRun, run_id)
    if run is None or run.owner_wallet_address != wallet_address or run.run_type != "spreadsheet_analysis":
        raise HTTPException(status_code=404, detail="analysis run not found")
    return run


def _owned_run_or_404(db: Session, wallet_address: str, run_id: str) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None or run.owner_wallet_address != wallet_address or run.run_type != "spreadsheet_analysis":
        raise HTTPException(status_code=404, detail="analysis run not found")
    return run


@router.get("/{run_id}/events", response_model=list[AgentRunEventRead])
def list_my_analysis_events(run_id: str, after: int = 0, wallet_address: str = Depends(get_current_wallet), db: Session = Depends(get_db)) -> list[AgentRunEventRead]:
    _owned_run_or_404(db, wallet_address, run_id)
    return list(db.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id).where(AgentRunEvent.sequence > max(0, after)).order_by(AgentRunEvent.sequence.asc())).all())


@router.get("/{run_id}/events/stream")
def stream_my_analysis_events(run_id: str, after: int = 0, wallet_address: str = Depends(get_current_wallet), db: Session = Depends(get_db)) -> StreamingResponse:
    _owned_run_or_404(db, wallet_address, run_id)
    def generate():
        cursor = max(0, after)
        while True:
            session = SessionLocal()
            try:
                run = session.get(AgentRun, run_id)
                if run is None or run.owner_wallet_address != wallet_address:
                    return
                events = list(session.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id == run_id).where(AgentRunEvent.sequence > cursor).order_by(AgentRunEvent.sequence.asc())).all())
                for event in events:
                    cursor = event.sequence
                    payload = AgentRunEventRead.model_validate(event).model_dump(mode="json")
                    yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if run.status in {"completed", "failed", "cancelled"}:
                    return
            finally:
                session.close()
            yield ": keep-alive\n\n"
            time.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{run_id}/artifacts", response_model=list[AgentRunArtifactRead])
def list_my_analysis_artifacts(run_id: str, wallet_address: str = Depends(get_current_wallet), db: Session = Depends(get_db)) -> list[AgentRunArtifactRead]:
    _owned_run_or_404(db, wallet_address, run_id)
    return list(db.scalars(select(AgentRunArtifact).where(AgentRunArtifact.run_id == run_id).order_by(AgentRunArtifact.created_at.asc(), AgentRunArtifact.id.asc())).all())
