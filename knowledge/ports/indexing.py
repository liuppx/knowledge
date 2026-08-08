from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session


@runtime_checkable
class IndexBackendPort(Protocol):
    """Minimal index contract used by ingestion and retrieval services."""

    backend_name: str

    def search(
        self,
        db: Session,
        wallet_address: str,
        kb_ids: list[int] | tuple[int, ...],
        query_vector: list[float],
        top_k: int,
        query_text: str | None = None,
        filters: dict | None = None,
    ) -> list[dict]:
        ...

    def index_chunks(self, payloads: list[dict]) -> None:
        ...

    def delete_vectors(self, vector_ids: list[str]) -> None:
        ...

    def health(self) -> dict:
        ...

    def close(self) -> None:
        ...
