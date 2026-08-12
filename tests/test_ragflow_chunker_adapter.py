from __future__ import annotations

from knowledge.adapters.ragflow import RAGFlowDocumentChunker
from knowledge.core.settings import get_settings
from knowledge.ports import DocumentChunkerPort
from knowledge.services.chunking import DocumentChunker
from knowledge.services.document_chunking import build_document_chunker


class ExplodingFallback:
    def chunk(self, file_name: str, parsed_text: str, config: dict):
        raise AssertionError(f"fallback should not chunk {file_name}")


class MarkerFallback:
    def chunk(self, file_name: str, parsed_text: str, config: dict):
        return []


def test_document_chunker_factory_defaults_to_local(monkeypatch) -> None:
    monkeypatch.delenv("DOCUMENT_CHUNKER_MODE", raising=False)
    get_settings.cache_clear()

    chunker = build_document_chunker()

    assert isinstance(chunker, DocumentChunker)


def test_document_chunker_factory_can_select_ragflow(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_CHUNKER_MODE", "ragflow")
    get_settings.cache_clear()

    chunker = build_document_chunker()

    assert isinstance(chunker, RAGFlowDocumentChunker)
    assert isinstance(chunker, DocumentChunkerPort)


def test_ragflow_chunker_uses_vendored_merge_logic() -> None:
    chunker = RAGFlowDocumentChunker(fallback=ExplodingFallback(), delimiter="\n。")

    chunks = chunker.chunk(
        "note.txt",
        "第一段。第二段。第三段。",
        {"chunk_size": 3, "chunk_overlap": 0},
    )

    assert len(chunks) >= 2
    assert all(chunk.metadata["chunk_strategy"] == "ragflow_token_text" for chunk in chunks)
    assert "第一段" in chunks[0].text


def test_ragflow_chunker_falls_back_when_text_is_empty() -> None:
    chunker = RAGFlowDocumentChunker(fallback=MarkerFallback())

    assert chunker.chunk("empty.txt", "", {"chunk_size": 3}) == []
