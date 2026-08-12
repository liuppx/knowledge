#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

"""Lazy parser exports for Knowledge's vendored RAGFlow snapshot.

Upstream RAGFlow imports every parser from this module. In Knowledge, the
vendored snapshot is adapted incrementally, so importing text or JSON parsing
should not require optional PDF, DOCX, PPT, or OCR dependencies. Keep the public
names compatible while importing each parser only when requested.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "PdfParser": ("deepdoc.parser.pdf_parser", "RAGFlowPdfParser"),
    "PlainParser": ("deepdoc.parser.pdf_parser", "PlainParser"),
    "DocxParser": ("deepdoc.parser.docx_parser", "RAGFlowDocxParser"),
    "EpubParser": ("deepdoc.parser.epub_parser", "RAGFlowEpubParser"),
    "ExcelParser": ("deepdoc.parser.excel_parser", "RAGFlowExcelParser"),
    "PptParser": ("deepdoc.parser.ppt_parser", "RAGFlowPptParser"),
    "HtmlParser": ("deepdoc.parser.html_parser", "RAGFlowHtmlParser"),
    "JsonParser": ("deepdoc.parser.json_parser", "RAGFlowJsonParser"),
    "MarkdownParser": ("deepdoc.parser.markdown_parser", "RAGFlowMarkdownParser"),
    "MarkdownElementExtractor": ("deepdoc.parser.markdown_parser", "MarkdownElementExtractor"),
    "TxtParser": ("deepdoc.parser.txt_parser", "RAGFlowTxtParser"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = list(_EXPORTS)
