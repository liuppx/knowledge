from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from knowledge.models import AgentRunEvent, AgentRunStep
from knowledge.utils.time import utc_now


class AgentRunProgressService:
    def event(
        self,
        db: Session,
        run_id: str,
        event_type: str,
        *,
        stage: str = "",
        progress: int = 0,
        message: str = "",
        retryable: bool = False,
        payload: dict | None = None,
        commit: bool = True,
    ) -> AgentRunEvent:
        sequence = int(db.scalar(select(func.max(AgentRunEvent.sequence)).where(AgentRunEvent.run_id == run_id)) or 0) + 1
        item = AgentRunEvent(
            run_id=run_id,
            sequence=sequence,
            event_type=str(event_type or "progress")[:64],
            stage=str(stage or "")[:64],
            progress=max(0, min(100, int(progress))),
            message=str(message or "")[:500],
            retryable=bool(retryable),
            payload_json=dict(payload or {}),
        )
        db.add(item)
        if commit:
            db.commit()
            db.refresh(item)
        return item

    def start_step(self, db: Session, run_id: str, step_type: str) -> AgentRunStep:
        sequence = int(db.scalar(select(func.max(AgentRunStep.sequence)).where(AgentRunStep.run_id == run_id)) or 0) + 1
        item = AgentRunStep(run_id=run_id, sequence=sequence, step_type=step_type, status="running")
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def finish_step(db: Session, step: AgentRunStep, *, metrics: dict | None = None) -> AgentRunStep:
        step.status = "completed"
        step.metrics_json = dict(metrics or {})
        step.error_summary = ""
        step.finished_at = utc_now()
        db.commit()
        db.refresh(step)
        return step

    @staticmethod
    def fail_step(db: Session, step: AgentRunStep, exc: Exception) -> AgentRunStep:
        step.status = "failed"
        step.error_summary = (str(exc).strip() or exc.__class__.__name__)[:2000]
        step.finished_at = utc_now()
        db.commit()
        db.refresh(step)
        return step
