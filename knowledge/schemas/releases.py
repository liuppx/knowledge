from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from knowledge.schemas.future_domain import KBReleaseItemRead, KBReleaseRead


class ReleasePublishRequest(BaseModel):
    version: str
    release_note: str = ""


class ReleaseHotfixRequest(BaseModel):
    version: str
    release_note: str = ""
    knowledge_item_ids: list[int] = Field(default_factory=list)
    base_release_id: int | None = None


class ReleaseRollbackRequest(BaseModel):
    version: str
    release_note: str = ""


class ReleaseDetailResponse(BaseModel):
    release: KBReleaseRead
    items: list[KBReleaseItemRead] = Field(default_factory=list)


class ReleaseDiffCounts(BaseModel):
    added: int = 0
    removed: int = 0
    changed: int = 0
    unchanged: int = 0


class ReleaseDiffEntry(BaseModel):
    knowledge_item_id: int
    change: Literal["added", "removed", "changed", "unchanged"]
    item_type: str
    title: str
    base_title: str | None = None
    base_revision_id: int | None = None
    target_revision_id: int | None = None
    base_version_hash: str | None = None
    target_version_hash: str | None = None


class ReleaseDiffResponse(BaseModel):
    base_release: KBReleaseRead
    release: KBReleaseRead
    counts: ReleaseDiffCounts
    entries: list[ReleaseDiffEntry] = Field(default_factory=list)
