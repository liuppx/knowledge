from __future__ import annotations

from typing import Protocol


class ArtifactStorePort(Protocol):
    """Store binary run artifacts; Knowledge retains metadata and provenance."""

    def put(self, path: str, content: bytes, content_type: str | None = None) -> dict:
        ...

    def get(self, path: str) -> bytes:
        ...

    def delete(self, path: str) -> None:
        ...
