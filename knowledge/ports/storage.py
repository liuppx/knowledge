from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class AssetAccessContext:
    """Authorization already resolved by Knowledge for one asset operation."""

    owner_id: str
    authorization: object
    credential_root: str
    trace_id: str = ""
    fallback_authorization: object | None = None


@dataclass(frozen=True)
class AssetReference:
    """Provider-neutral reference and integrity metadata for a stored object."""

    provider: str
    object_id: str
    version_id: str | None = None
    etag: str | None = None
    sha256: str | None = None
    size: int | None = None
    content_type: str | None = None
    modified_at: datetime | None = None


@dataclass(frozen=True)
class AssetEntry:
    reference: AssetReference
    name: str
    entry_type: str = "file"


class AssetStoreError(RuntimeError):
    """Stable error surface for storage adapters."""

    def __init__(self, code: str, message: str = "asset storage operation failed") -> None:
        self.code = code
        super().__init__(message)


class AssetStorePort(Protocol):
    """Discover, read and write assets without exposing a storage protocol."""

    def list(self, context: AssetAccessContext, prefix: str) -> list[AssetEntry]:
        ...

    def stat(self, context: AssetAccessContext, reference: AssetReference | str) -> AssetReference:
        ...

    def read(self, context: AssetAccessContext, reference: AssetReference | str) -> bytes:
        ...

    def write(
        self,
        context: AssetAccessContext,
        target_dir: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
        *,
        overwrite: bool = False,
        if_match: str | None = None,
    ) -> AssetReference:
        ...


# Kept as an import alias for any in-repository modules that adopted the first
# artifact-only draft of this port.
ArtifactStorePort = AssetStorePort
