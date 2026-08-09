from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.api.deps import get_current_wallet
from knowledge.db.session import get_db
from knowledge.models import AgentRun
from knowledge.schemas.agent_runs import AgentRunRead


router = APIRouter(prefix="/analysis-runs", tags=["analysis_runs"])


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
