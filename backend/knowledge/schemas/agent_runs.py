from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentRunCreateRequest(BaseModel):
    session_id: str = ""
    external_id: str | None = None
    run_type: str = "research"
    inputs: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AgentRunContextUpdateRequest(BaseModel):
    context: list[dict] = Field(default_factory=list)


class AgentRunFinishRequest(BaseModel):
    error_summary: str = ""


class AgentRunRead(BaseModel):
    id: str
    owner_wallet_address: str
    service_principal_id: int
    session_id: str
    external_id: str | None = None
    run_type: str
    status: str
    warehouse_run_path: str
    input_manifest_json: list = Field(default_factory=list)
    context_manifest_json: list = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)
    error_summary: str
    manifest_sync_status: str
    manifest_synced_at: datetime | None = None
    manifest_sync_error: str
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentRunArtifactRead(BaseModel):
    id: int
    run_id: str
    artifact_key: str
    artifact_type: str
    role: str
    status: str
    warehouse_path: str
    file_name: str
    content_type: str
    size: int
    sha256: str
    generated_by_json: dict = Field(default_factory=dict)
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
