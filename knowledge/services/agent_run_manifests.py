from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.models import AgentRun, AgentRunArtifact, ServicePrincipal
from knowledge.services.warehouse_access import WarehouseAccessService
from knowledge.utils.time import utc_now


class AgentRunManifestService:
    def __init__(self, warehouse_access_service: WarehouseAccessService | None = None) -> None:
        self.warehouse_access_service = warehouse_access_service or WarehouseAccessService()

    def sync(self, db: Session, run: AgentRun) -> AgentRun:
        try:
            resolved = self.warehouse_access_service.resolve_write_access(db, run.owner_wallet_address, run.warehouse_run_path)
            gateway = self.warehouse_access_service.warehouse_gateway
            gateway.ensure_app_space(
                run.owner_wallet_address,
                auth=resolved.auth,
                base_path=resolved.credential.root_path,
                target_path=run.warehouse_run_path,
            )
            gateway.upload_file(
                run.owner_wallet_address,
                run.warehouse_run_path,
                "manifest.json",
                self.render(db, run),
                auth=resolved.auth,
            )
            run.manifest_sync_status = "synced"
            run.manifest_synced_at = utc_now()
            run.manifest_sync_error = ""
            self.warehouse_access_service.mark_access_success(resolved)
        except Exception as exc:  # noqa: BLE001
            run.manifest_sync_status = "failed"
            run.manifest_sync_error = self._error_summary(exc)
        db.commit()
        db.refresh(run)
        return run

    def render(self, db: Session, run: AgentRun) -> bytes:
        principal = db.get(ServicePrincipal, run.service_principal_id)
        artifacts = list(
            db.scalars(
                select(AgentRunArtifact)
                .where(AgentRunArtifact.run_id == run.id)
                .order_by(AgentRunArtifact.created_at.asc(), AgentRunArtifact.id.asc())
            ).all()
        )
        payload = {
            "schema": "knowledge.agent-run.v1",
            "runId": run.id,
            "runType": run.run_type,
            "status": run.status,
            "servicePrincipal": {
                "id": run.service_principal_id,
                "serviceId": principal.service_id if principal is not None else "",
            },
            "sessionId": run.session_id,
            "externalId": run.external_id,
            "startedAt": self._time(run.started_at),
            "finishedAt": self._time(run.finished_at),
            "inputs": list(run.input_manifest_json or []),
            "context": list(run.context_manifest_json or []),
            "artifacts": [self._artifact(item) for item in artifacts],
            "metadata": dict(run.metadata_json or {}),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")

    @staticmethod
    def _artifact(item: AgentRunArtifact) -> dict:
        return {
            "key": item.artifact_key,
            "type": item.artifact_type,
            "role": item.role,
            "status": item.status,
            "warehousePath": item.warehouse_path,
            "fileName": item.file_name,
            "contentType": item.content_type,
            "size": item.size,
            "sha256": item.sha256,
            "generatedBy": dict(item.generated_by_json or {}),
            "metadata": dict(item.metadata_json or {}),
        }

    @staticmethod
    def _time(value) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _error_summary(exc: Exception) -> str:
        text = str(exc).strip() or exc.__class__.__name__
        return text[:2000]
