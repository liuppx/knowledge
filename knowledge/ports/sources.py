from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol


@dataclass(frozen=True)
class SourceAssetRef:
    """Source metadata normalized before it enters Knowledge's domain model."""

    path: str
    name: str
    entry_type: str = "file"
    size: int | None = None
    checksum: str | None = None
    version: str | None = None
    modified_at: datetime | None = None
    content_type: str | None = None


class SourceConnectorPort(Protocol):
    """Discover source assets without exposing a third-party data model."""

    def list_assets(self, root_path: str) -> Iterable[SourceAssetRef]:
        ...

    def read_asset(self, asset: SourceAssetRef) -> bytes:
        ...

    def health(self) -> dict:
        ...
