from __future__ import annotations

from contextlib import contextmanager
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Iterator

from knowledge.ports import DocumentParserPort
from knowledge.services.parser import DocumentParser


VENDORED_RAGFLOW_ROOT = Path(__file__).resolve().parents[2] / "third_party" / "ragflow"


class RAGFlowDocumentParser:
    """Document parser adapter for the vendored RAGFlow parser snapshot.

    The copied RAGFlow modules still use upstream absolute imports such as
    ``deepdoc`` and ``rag``. This adapter scopes that import path to parser calls
    and falls back to the existing Knowledge parser if a vendored parser or one
    of its optional dependencies is unavailable.
    """

    def __init__(
        self,
        fallback: DocumentParserPort | None = None,
        *,
        chunk_token_num: int = 512,
        delimiter: str = "\n!?;。；！？",
    ) -> None:
        self.fallback = fallback or DocumentParser()
        self.chunk_token_num = int(chunk_token_num)
        self.delimiter = delimiter

    def parse(self, file_name: str, content: bytes) -> str:
        suffix = Path(file_name).suffix.lower()
        try:
            if suffix in {".txt", ".log"}:
                parsed = self._parse_text(file_name, content)
            elif suffix in {".md", ".markdown"}:
                parsed = self._parse_markdown(content)
            elif suffix in {".html", ".htm"}:
                parsed = self._parse_html(file_name, content)
            elif suffix == ".json":
                parsed = self._parse_json(content)
            else:
                parsed = ""
        except Exception:
            parsed = ""
        if parsed.strip():
            return parsed
        return self.fallback.parse(file_name, content)

    def _parse_text(self, file_name: str, content: bytes) -> str:
        with _ragflow_import_path():
            parser_module = importlib.import_module("deepdoc.parser.txt_parser")
            parser = parser_module.RAGFlowTxtParser()
            sections = parser(
                file_name,
                binary=content,
                chunk_token_num=self.chunk_token_num,
                delimiter=self.delimiter,
            )
        return _stringify_sections(sections)

    def _parse_markdown(self, content: bytes) -> str:
        text = content.decode("utf-8", errors="ignore")
        with _ragflow_import_path():
            parser_module = importlib.import_module("deepdoc.parser.markdown_parser")
            parser = parser_module.RAGFlowMarkdownParser(chunk_token_num=self.chunk_token_num)
            remainder, tables = parser.extract_tables_and_remainder(text)
            sections = parser_module.MarkdownElementExtractor(remainder).extract_elements(delimiter=self.delimiter)
        return _stringify_sections([*sections, *tables])

    def _parse_html(self, file_name: str, content: bytes) -> str:
        with _ragflow_import_path():
            parser_module = importlib.import_module("deepdoc.parser.html_parser")
            parser = parser_module.RAGFlowHtmlParser()
            sections = parser(file_name, binary=content, chunk_token_num=self.chunk_token_num)
        return _stringify_sections(sections)

    def _parse_json(self, content: bytes) -> str:
        with _ragflow_import_path():
            parser_module = importlib.import_module("deepdoc.parser.json_parser")
            parser = parser_module.RAGFlowJsonParser(max_chunk_size=self.chunk_token_num)
            sections = parser(content)
        rendered = [_render_json_section(section) for section in sections]
        return _stringify_sections(rendered)


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


def _stringify_sections(sections: list[Any] | tuple[Any, ...]) -> str:
    lines: list[str] = []
    for section in sections:
        text = _section_text(section)
        if text:
            lines.append(text)
    return "\n\n".join(lines).strip()


def _section_text(section: Any) -> str:
    if section is None:
        return ""
    if isinstance(section, str):
        return section.strip()
    if isinstance(section, dict):
        return _render_json_section(section).strip()
    if isinstance(section, (list, tuple)):
        parts = [_section_text(item) for item in section]
        return "\n".join(part for part in parts if part).strip()
    return str(section).strip()


def _render_json_section(section: Any) -> str:
    if isinstance(section, str):
        return section
    return json.dumps(section, ensure_ascii=False, indent=2)
