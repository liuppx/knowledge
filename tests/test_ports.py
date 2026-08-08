from __future__ import annotations

from knowledge.ports import DocumentParserPort, IndexBackendPort, SourceAssetRef
from knowledge.services.parser import DocumentParser
from knowledge.services.vector_store import DBVectorStore


def test_default_parser_implements_document_parser_port() -> None:
    parser = DocumentParser()
    assert isinstance(parser, DocumentParserPort)


def test_default_index_implements_index_backend_port() -> None:
    store = DBVectorStore()
    assert isinstance(store, IndexBackendPort)


def test_source_asset_ref_keeps_external_metadata_small_and_stable() -> None:
    asset = SourceAssetRef(path="/docs/a.md", name="a.md", checksum="sha256:abc", version="v1")
    assert asset.path == "/docs/a.md"
    assert asset.checksum == "sha256:abc"
