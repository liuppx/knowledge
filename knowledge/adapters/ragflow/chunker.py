from __future__ import annotations

from contextlib import contextmanager
import importlib
import sys
from pathlib import Path
from typing import Iterator

from knowledge.ports import ChunkResult, DocumentChunkerPort
from knowledge.services.chunking import DocumentChunker
from knowledge.services.filetypes import infer_file_type


VENDORED_RAGFLOW_ROOT = Path(__file__).resolve().parents[2] / "third_party" / "ragflow"


class RAGFlowDocumentChunker:
    """Chunker adapter using vendored RAGFlow token merge helpers."""

    def __init__(self, fallback: DocumentChunkerPort | None = None, *, delimiter: str = "\n。；！？") -> None:
        self.fallback = fallback or DocumentChunker()
        self.delimiter = delimiter

    def chunk(self, file_name: str, parsed_text: str, config: dict) -> list[ChunkResult]:
        if not parsed_text.strip():
            return []
        try:
            chunks = self._chunk_with_ragflow(parsed_text, config)
        except Exception:
            chunks = []
        if chunks:
            file_type = infer_file_type(file_name)
            return [
                ChunkResult(
                    text=text,
                    metadata={
                        "chunk_strategy": f"ragflow_token_{file_type}",
                        "char_count": len(text),
                    },
                )
                for text in chunks
                if text.strip()
            ]
        return self.fallback.chunk(file_name, parsed_text, config)

    def _chunk_with_ragflow(self, parsed_text: str, config: dict) -> list[str]:
        chunk_size = max(1, int(config.get("chunk_size", 800)))
        overlap = max(0, int(config.get("chunk_overlap", 0)))
        overlapped_percent = min(0.95, overlap / chunk_size) if chunk_size else 0
        with _ragflow_import_path():
            nlp = importlib.import_module("rag.nlp")
            chunks = nlp.naive_merge(
                parsed_text,
                chunk_token_num=chunk_size,
                delimiter=self.delimiter,
                overlapped_percent=overlapped_percent,
            )
        return [str(chunk).strip() for chunk in chunks if str(chunk).strip()]


@contextmanager
def _ragflow_import_path() -> Iterator[None]:
    root = str(VENDORED_RAGFLOW_ROOT)
    inserted = False
    if root not in sys.path:
        sys.path.insert(0, root)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(root)
            except ValueError:
                pass
