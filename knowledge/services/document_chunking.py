from __future__ import annotations

from knowledge.adapters.ragflow import RAGFlowDocumentChunker
from knowledge.core.settings import get_settings
from knowledge.ports import DocumentChunkerPort
from knowledge.services.chunking import DocumentChunker


def build_document_chunker() -> DocumentChunkerPort:
    settings = get_settings()
    fallback = DocumentChunker()
    if settings.document_chunker_mode.lower() == "ragflow":
        return RAGFlowDocumentChunker(
            fallback=fallback,
            delimiter=settings.ragflow_chunker_delimiter,
        )
    return fallback
