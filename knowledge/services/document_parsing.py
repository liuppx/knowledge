from __future__ import annotations

from knowledge.adapters.ragflow import RAGFlowDocumentParser
from knowledge.core.settings import get_settings
from knowledge.ports import DocumentParserPort
from knowledge.services.parser import DocumentParser


def build_document_parser() -> DocumentParserPort:
    settings = get_settings()
    fallback = DocumentParser()
    if settings.document_parser_mode.lower() == "ragflow":
        return RAGFlowDocumentParser(
            fallback=fallback,
            chunk_token_num=settings.ragflow_parser_chunk_token_num,
            delimiter=settings.ragflow_parser_delimiter,
        )
    return fallback
