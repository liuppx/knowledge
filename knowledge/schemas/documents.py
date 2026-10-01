from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentRead(BaseModel):
    id: int
    source_path: str
    source_file_name: str
    file_type: str
    source_kind: str
    parse_status: str
    chunk_count: int = 0
    last_indexed_at: datetime | None = None


class DocumentChunkRead(BaseModel):
    id: int
    chunk_index: int
    text: str
    metadata: dict | None = None
    created_at: datetime
    embedding_model: str | None = None
    index_status: str | None = None


class DocumentDetailRead(DocumentRead):
    created_at: datetime
    updated_at: datetime
    source_etag_or_mtime: str | None = None
    chunks: list[DocumentChunkRead] = Field(default_factory=list)
