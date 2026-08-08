from __future__ import annotations

from knowledge.adapters.ragflow import RAGFlowDocumentParser
from knowledge.core.settings import get_settings
from knowledge.ports import DocumentParserPort
from knowledge.services.document_parsing import build_document_parser
from knowledge.services.parser import DocumentParser


class ExplodingFallback:
    def parse(self, file_name: str, content: bytes) -> str:
        raise AssertionError(f"fallback should not parse {file_name}")


class MarkerFallback:
    def parse(self, file_name: str, content: bytes) -> str:
        return f"fallback:{file_name}:{content.decode('utf-8', errors='ignore')}"


def test_document_parser_factory_defaults_to_local(monkeypatch) -> None:
    monkeypatch.delenv("DOCUMENT_PARSER_MODE", raising=False)
    get_settings.cache_clear()

    parser = build_document_parser()

    assert isinstance(parser, DocumentParser)


def test_document_parser_factory_can_select_ragflow(monkeypatch) -> None:
    monkeypatch.setenv("DOCUMENT_PARSER_MODE", "ragflow")
    get_settings.cache_clear()

    parser = build_document_parser()

    assert isinstance(parser, RAGFlowDocumentParser)
    assert isinstance(parser, DocumentParserPort)


def test_ragflow_text_parser_uses_vendored_code() -> None:
    parser = RAGFlowDocumentParser(fallback=ExplodingFallback(), chunk_token_num=8)

    parsed = parser.parse("note.txt", "第一段。第二段。".encode("utf-8"))

    assert "第一段" in parsed
    assert "第二段" in parsed


def test_ragflow_json_parser_uses_vendored_code() -> None:
    parser = RAGFlowDocumentParser(fallback=ExplodingFallback(), chunk_token_num=64)

    parsed = parser.parse("data.json", b'{"name":"Knowledge","items":[1,2]}')

    assert "Knowledge" in parsed
    assert "items" in parsed


def test_ragflow_parser_falls_back_for_unsupported_files() -> None:
    parser = RAGFlowDocumentParser(fallback=MarkerFallback())

    parsed = parser.parse("file.bin", b"abc")

    assert parsed == "fallback:file.bin:abc"
