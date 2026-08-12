from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ChunkResult:
    text: str
    metadata: dict


@runtime_checkable
class DocumentChunkerPort(Protocol):
    """Split parsed document text into Knowledge chunks."""

    def chunk(self, file_name: str, parsed_text: str, config: dict) -> list[ChunkResult]:
        ...
