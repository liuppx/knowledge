from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DocumentParserPort(Protocol):
    """Parse an asset while keeping the source identity outside the parser."""

    def parse(self, file_name: str, content: bytes) -> str:
        ...
