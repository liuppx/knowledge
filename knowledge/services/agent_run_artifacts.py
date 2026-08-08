from __future__ import annotations

import hashlib
import re
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.models import AgentRunArtifact, ServicePrincipal
from knowledge.models.entities import AGENT_ARTIFACT_STATUSES
from knowledge.services.agent_runs import AgentRunService
from knowledge.services.warehouse_access import WarehouseAccessService


class AgentRunArtifactService:
    KEY_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
    ALLOWED_TYPES = {"report", "code", "image", "data", "log", "other"}

    def __init__(
        self,
        run_service: AgentRunService | None = None,
        warehouse_access_service: WarehouseAccessService | None = None,
    ) -> None:
        self.run_service = run_service or AgentRunService()
        self.warehouse_access_service = warehouse_access_service or WarehouseAccessService()

    def upload(
        self,
        db: Session,
        principal: ServicePrincipal,
        run_id: str,
        *,
        artifact_key: str,
        artifact_type: str,
        role: str,
        status: str,
        file_name: str,
        content_type: str,
        content: bytes,
        generated_by: dict | None = None,
        metadata: dict | None = None,
    ) -> AgentRunArtifact:
        run = self.run_service.get_run(db, principal, run_id)
        self.run_service._require_running(run)
        key = str(artifact_key or "").strip()
        if not self.KEY_PATTERN.fullmatch(key):
            raise ValueError("artifact_key is invalid")
        normalized_type = str(artifact_type or "other").strip().lower()
        if normalized_type not in self.ALLOWED_TYPES:
            raise ValueError(f"artifact_type must be one of: {', '.join(sorted(self.ALLOWED_TYPES))}")
        normalized_status = str(status or "draft").strip().lower()
        if normalized_status not in AGENT_ARTIFACT_STATUSES:
            raise ValueError(f"artifact status must be one of: {', '.join(AGENT_ARTIFACT_STATUSES)}")
        if not content:
            raise ValueError("artifact file is empty")
        existing = db.scalar(
            select(AgentRunArtifact)
            .where(AgentRunArtifact.run_id == run.id)
            .where(AgentRunArtifact.artifact_key == key)
        )
        if existing is not None:
            raise ValueError("artifact_key already exists in run")
        suffix = PurePath(str(file_name or "").strip()).suffix[:32]
        stored_name = key + suffix
        target_dir = f"{run.warehouse_run_path}/artifacts"
        resolved = self.warehouse_access_service.resolve_write_access(db, run.owner_wallet_address, target_dir)
        gateway = self.warehouse_access_service.warehouse_gateway
        gateway.ensure_app_space(
            run.owner_wallet_address,
            auth=resolved.auth,
            base_path=resolved.credential.root_path,
            target_path=target_dir,
        )
        warehouse_path = gateway.upload_file(
            run.owner_wallet_address,
            target_dir,
            stored_name,
            content,
            auth=resolved.auth,
        )
        item = AgentRunArtifact(
            run_id=run.id,
            artifact_key=key,
            artifact_type=normalized_type,
            role=str(role or "output").strip()[:128] or "output",
            status=normalized_status,
            warehouse_path=warehouse_path,
            file_name=PurePath(str(file_name or stored_name)).name[:255] or stored_name,
            content_type=str(content_type or "application/octet-stream").strip()[:255],
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            generated_by_json=dict(generated_by or {}),
            metadata_json=dict(metadata or {}),
        )
        db.add(item)
        run.manifest_sync_status = "pending"
        self.warehouse_access_service.mark_access_success(resolved)
        db.commit()
        db.refresh(item)
        return item
