from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.api.deps import get_current_wallet
from knowledge.db.session import get_db
from knowledge.models import AgentRun, ServicePrincipal
from knowledge.schemas.agent_runs import AgentRunRead
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
