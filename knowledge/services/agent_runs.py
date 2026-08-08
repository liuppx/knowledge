from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from knowledge.models import AgentRun, AgentRunInput, EvidenceUnit, KnowledgeItem, RetrievalLog, ServiceGrant, ServicePrincipal
from knowledge.models.entities import AGENT_RUN_STATUSES, AGENT_RUN_TYPES
from knowledge.services.warehouse_scope import warehouse_app_path
from knowledge.services.agent_run_progress import AgentRunProgressService
from knowledge.utils.time import utc_now


class AgentRunService:
    TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

    def __init__(self) -> None:
        self.progress = AgentRunProgressService()

    def create_run(
        self,
        db: Session,
        principal: ServicePrincipal,
        *,
        session_id: str = "",
        external_id: str | None = None,
        run_type: str = "research",
        inputs: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> AgentRun:
        normalized_type = str(run_type or "").strip().lower()
        if normalized_type not in AGENT_RUN_TYPES:
            raise ValueError(f"run_type must be one of: {', '.join(AGENT_RUN_TYPES)}")
        normalized_external_id = str(external_id or "").strip() or None
        if normalized_external_id:
            existing = db.scalar(
                select(AgentRun)
                .where(AgentRun.service_principal_id == principal.id)
                .where(AgentRun.external_id == normalized_external_id)
            )
            if existing is not None:
                return existing
        run_id = self._new_run_id()
        normalized_inputs = self._normalize_inputs(inputs or [], require_spreadsheet=normalized_type == "spreadsheet_analysis")
        run = AgentRun(
            id=run_id,
            owner_wallet_address=principal.owner_wallet_address,
            service_principal_id=principal.id,
            session_id=str(session_id or "").strip(),
            external_id=normalized_external_id,
            run_type=normalized_type,
            status="queued" if normalized_type == "spreadsheet_analysis" else "running",
            warehouse_run_path=warehouse_app_path(f"runs/{run_id}"),
            input_manifest_json=normalized_inputs,
            context_manifest_json=[],
            metadata_json=dict(metadata or {}),
            manifest_sync_status="pending",
        )
        db.add(run)
        for item in normalized_inputs:
            db.add(
                AgentRunInput(
                    run_id=run_id,
                    input_key=item["inputKey"],
                    kind=item["kind"],
                    role=item["role"],
                    warehouse_path=item["warehousePath"],
                    version_id=item["versionId"],
                    etag=item["etag"],
                    sha256=item["sha256"],
                    size=item["size"],
                    content_type=item["contentType"],
                    metadata_json=item["metadata"],
                )
            )
        if normalized_type == "spreadsheet_analysis":
            self.progress.event(
                db,
                run_id,
                "run.queued",
                stage="queued",
                progress=0,
                message="分析任务已进入队列",
                commit=False,
            )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if normalized_external_id:
                existing = db.scalar(
                    select(AgentRun)
                    .where(AgentRun.service_principal_id == principal.id)
                    .where(AgentRun.external_id == normalized_external_id)
                )
                if existing is not None:
                    return existing
            raise
        db.refresh(run)
        return run

    def get_run(self, db: Session, principal: ServicePrincipal, run_id: str) -> AgentRun:
        run = db.get(AgentRun, str(run_id or "").strip())
        if run is None or run.service_principal_id != principal.id:
            raise LookupError("agent run not found")
        return run

    def update_context(self, db: Session, principal: ServicePrincipal, run_id: str, context: list[dict]) -> AgentRun:
        run = self.get_run(db, principal, run_id)
        self._require_running(run)
        normalized_context = list(context or [])
        self._validate_context(db, principal, run, normalized_context)
        run.context_manifest_json = normalized_context
        run.manifest_sync_status = "pending"
        db.commit()
        db.refresh(run)
        return run

    def finish_run(
        self,
        db: Session,
        principal: ServicePrincipal,
        run_id: str,
        status: str,
        *,
        error_summary: str = "",
    ) -> AgentRun:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in self.TERMINAL_STATUSES:
            raise ValueError("status must be completed, failed, or cancelled")
        run = self.get_run(db, principal, run_id)
        if run.status in self.TERMINAL_STATUSES:
            if run.status == normalized_status:
                return run
            raise ValueError(f"agent run is already {run.status}")
        if run.status not in AGENT_RUN_STATUSES:
            raise ValueError(f"invalid agent run status: {run.status}")
        run.status = normalized_status
        run.error_summary = str(error_summary or "").strip()[:2000] if normalized_status == "failed" else ""
        run.finished_at = utc_now()
        run.manifest_sync_status = "pending"
        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def _require_running(run: AgentRun) -> None:
        if run.status != "running":
            raise ValueError(f"agent run is already {run.status}")

    @staticmethod
    def _normalize_inputs(inputs: list[dict], *, require_spreadsheet: bool) -> list[dict]:
        if require_spreadsheet and not inputs:
            raise ValueError("spreadsheet_analysis requires at least one input")
        normalized: list[dict] = []
        for index, raw in enumerate(inputs):
            if not isinstance(raw, dict):
                raise ValueError(f"inputs[{index}] must be an object")
            kind = str(raw.get("kind") or "warehouse_asset").strip()
            path = str(raw.get("warehousePath") or raw.get("warehouse_path") or "").strip()
            if kind != "warehouse_asset" or not path.startswith("/"):
                raise ValueError(f"inputs[{index}] must reference a warehouse asset")
            if require_spreadsheet and not path.lower().endswith((".csv", ".xlsx")):
                raise ValueError(f"inputs[{index}] must be a CSV or XLSX file")
            sha256 = str(raw.get("sha256") or "").strip().lower()
            if sha256 and (len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256)):
                raise ValueError(f"inputs[{index}].sha256 is invalid")
            normalized.append(
                {
                    "inputKey": str(raw.get("inputKey") or raw.get("input_key") or f"input-{index + 1}")[:128],
                    "kind": kind,
                    "role": str(raw.get("role") or "source")[:64],
                    "warehousePath": path,
                    "versionId": str(raw.get("versionId") or raw.get("version_id") or "")[:255],
                    "etag": str(raw.get("etag") or "")[:255],
                    "sha256": sha256,
                    "size": max(0, int(raw.get("size") or 0)),
                    "contentType": str(raw.get("contentType") or raw.get("content_type") or "application/octet-stream")[:255],
                    "metadata": dict(raw.get("metadata") or {}),
                }
            )
        return normalized

    def _validate_context(self, db: Session, principal: ServicePrincipal, run: AgentRun, context: list[dict]) -> None:
        allowed_kinds = {"warehouse_asset", "evidence", "knowledge_item", "retrieval_log", "tool_output"}
        active_grants = {
            grant.kb_id
            for grant in db.scalars(
                select(ServiceGrant)
                .where(ServiceGrant.service_principal_id == principal.id)
                .where(ServiceGrant.grant_status == "active")
            ).all()
            if grant.expires_at is None or grant.expires_at > utc_now()
        }
        for index, reference in enumerate(context):
            if not isinstance(reference, dict):
                raise ValueError(f"context[{index}] must be an object")
            kind = str(reference.get("kind") or "").strip()
            if kind not in allowed_kinds:
                raise ValueError(f"context[{index}].kind is invalid")
            reference_id = str(reference.get("referenceId") or "").strip()
            if kind in {"warehouse_asset", "tool_output"}:
                continue
            if not reference_id.isdigit():
                raise ValueError(f"context[{index}].referenceId must be an integer id")
            object_id = int(reference_id)
            if kind == "retrieval_log":
                item = db.get(RetrievalLog, object_id)
                if item is None or item.service_principal_id != principal.id:
                    raise ValueError(f"context[{index}] retrieval log is not accessible")
                if item.agent_run_id not in {None, run.id}:
                    raise ValueError(f"context[{index}] retrieval log belongs to another run")
                item.agent_run_id = run.id
                continue
            if kind == "evidence":
                item = db.get(EvidenceUnit, object_id)
                kb_id = item.kb_id if item is not None else None
            else:
                item = db.get(KnowledgeItem, object_id)
                kb_id = item.kb_id if item is not None else None
            if kb_id is None or kb_id not in active_grants:
                raise ValueError(f"context[{index}] knowledge reference is not granted")

    @staticmethod
    def _new_run_id() -> str:
        return "run_" + secrets.token_hex(16)
