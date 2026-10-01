from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OpsOverviewResponse(BaseModel):
    knowledge_bases: int = 0
    documents: int = 0
    chunks: int = 0
    tasks_total: int = 0
    tasks_pending: int = 0
    tasks_running: int = 0
    tasks_claimed_stale: int = 0
    avg_task_wait_ms: int = 0
    avg_task_run_ms: int = 0
    long_term_memories: int = 0
    short_term_memories: int = 0
    memory_ingestions: int = 0
    retrieval_logs: int = 0
    source_assets_missing: int = 0
    source_assets_stale: int = 0
    uploads: int = 0


class StoresHealthResponse(BaseModel):
    # Field names mirror settings (model_provider_*); opt out of pydantic's "model_" namespace.
    model_config = {"protected_namespaces": ()}

    database: str
    vector_store_mode: str
    vector_store_status: dict = Field(default_factory=dict)
    model_provider_mode: str
    model_provider_status: str
    object_storage_endpoint: str
    object_storage_region: str
    # Deprecated fields retained for old console clients.
    warehouse_gateway_mode: str = ""
    warehouse_base_url: str = ""


class WorkerStatusRead(BaseModel):
    worker_name: str
    status: str
    last_seen_at: datetime
    last_processed_at: datetime | None = None
    processed_count: int = 0
    last_error: str | None = None
    active_tasks_count: int = 0


class TaskFailureRead(BaseModel):
    id: int
    kb_id: int
    task_type: str
    status: str
    trace_id: str = ""
    source_paths: list[str] = Field(default_factory=list)
    error_message: str = ""
    stats_json: dict = Field(default_factory=dict)
    finished_at: datetime | None = None
    created_at: datetime
