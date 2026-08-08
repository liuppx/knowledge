from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from knowledge.adapters.onyx import OnyxDocumentMapper, OnyxLocalFileConnector
from knowledge.ports import SourceConnectorPort


@dataclass
class DocumentLike:
    id: str
    semantic_identifier: str
    title: str
    doc_updated_at: datetime
    metadata: dict

    def content_hash(self) -> str:
        return "hash-123"


def test_onyx_document_mapper_normalizes_document_like_object() -> None:
    mapper = OnyxDocumentMapper()
    updated_at = datetime(2026, 8, 8, tzinfo=timezone.utc)

    asset = mapper.to_asset_ref(
        DocumentLike(
            id="doc-1",
            semantic_identifier="Roadmap",
            title="Ignored when semantic id exists",
            doc_updated_at=updated_at,
            metadata={"content_type": "text/markdown", "size": "42"},
        ),
        path_prefix="onyx/docs",
    )

    assert asset.path == "onyx/docs/doc-1"
    assert asset.name == "Roadmap"
    assert asset.size == 42
    assert asset.checksum == "hash-123"
    assert asset.version == updated_at.isoformat()
    assert asset.content_type == "text/markdown"


def test_onyx_document_mapper_normalizes_dict() -> None:
    mapper = OnyxDocumentMapper()

    asset = mapper.to_asset_ref(
        {
            "id": "web-1",
            "title": "Homepage",
            "updated_at": "2026-08-08T00:00:00Z",
            "metadata": {"mime_type": "text/html"},
        }
    )

    assert asset.path == "onyx/web-1"
    assert asset.name == "Homepage"
    assert asset.modified_at is not None
    assert asset.content_type == "text/html"


def test_onyx_local_file_connector_lists_and_reads_files(tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    first = docs / "a.txt"
    second = docs / "b.md"
    first.write_text("alpha", encoding="utf-8")
    second.write_text("beta", encoding="utf-8")
    connector = OnyxLocalFileConnector(tmp_path)

    assets = connector.list_assets("docs")
    file_assets = [asset for asset in assets if asset.entry_type == "file"]

    assert isinstance(connector, SourceConnectorPort)
    assert assets[0].path == "docs"
    assert assets[0].entry_type == "directory"
    assert [asset.path for asset in file_assets] == ["docs/a.txt", "docs/b.md"]
    assert file_assets[0].checksum.startswith("sha256:")
    assert connector.read_asset(file_assets[1]) == b"beta"
    assert connector.health()["status"] == "ok"


def test_onyx_local_file_connector_rejects_path_escape(tmp_path) -> None:
    connector = OnyxLocalFileConnector(tmp_path)

    with pytest.raises(ValueError, match="escapes"):
        connector.list_assets("../outside")
