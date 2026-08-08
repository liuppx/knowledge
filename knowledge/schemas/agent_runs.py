from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SpreadsheetFilterRequest(BaseModel):
    column: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "in", "is_null", "not_null"] = "eq"
    value: Any = None


class SpreadsheetAggregationRequest(BaseModel):
    column: str
    op: Literal["count", "sum", "avg", "min", "max"]
    alias: str | None = None


class SpreadsheetSortRequest(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class SpreadsheetAnalysisPlanRequest(BaseModel):
    select: list[str] = Field(default_factory=list)
    filters: list[SpreadsheetFilterRequest] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[SpreadsheetAggregationRequest] = Field(default_factory=list)
    sort: list[SpreadsheetSortRequest] = Field(default_factory=list)
    limit: int = Field(default=1000, ge=1, le=10000)


class SpreadsheetAnalysisConstraints(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_rows: int | None = Field(default=None, ge=1)
    allow_sampling: bool = True
    output_formats: list[Literal["markdown", "csv", "xlsx", "png"]] = Field(default_factory=list)
    analysis_plan: SpreadsheetAnalysisPlanRequest | None = None


class AgentRunCreateRequest(BaseModel):
    session_id: str = ""
    external_id: str | None = None
    run_type: str = "research"
    inputs: list[dict] = Field(default_factory=list)
    intent: str = ""
    constraints: SpreadsheetAnalysisConstraints = Field(default_factory=SpreadsheetAnalysisConstraints)
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


class AgentRunInputRead(BaseModel):
    id: int
    input_key: str
    kind: str
    role: str
    warehouse_path: str
    version_id: str
    etag: str
    sha256: str
    size: int
    content_type: str
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentRunStepRead(BaseModel):
    id: int
    sequence: int
    step_type: str
    status: str
    metrics_json: dict = Field(default_factory=dict)
    error_summary: str
    started_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentRunEventRead(BaseModel):
    sequence: int
    event_type: str
    stage: str
    progress: int
    message: str
    retryable: bool
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}
