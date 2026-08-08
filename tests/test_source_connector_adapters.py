from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from knowledge.adapters.connectors import ConnectorDocumentMapper, GitHubRepositoryConnector, LocalFileConnector
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


def test_connector_document_mapper_normalizes_document_like_object() -> None:
    mapper = ConnectorDocumentMapper()
    updated_at = datetime(2026, 8, 8, tzinfo=timezone.utc)

    asset = mapper.to_asset_ref(
        DocumentLike(
            id="doc-1",
            semantic_identifier="Roadmap",
            title="Ignored when semantic id exists",
            doc_updated_at=updated_at,
            metadata={"content_type": "text/markdown", "size": "42"},
        ),
        path_prefix="connector/docs",
    )

    assert asset.path == "connector/docs/doc-1"
    assert asset.name == "Roadmap"
    assert asset.size == 42
    assert asset.checksum == "hash-123"
    assert asset.version == updated_at.isoformat()
    assert asset.content_type == "text/markdown"


def test_connector_document_mapper_normalizes_dict() -> None:
    mapper = ConnectorDocumentMapper()

    asset = mapper.to_asset_ref(
        {
            "id": "web-1",
            "title": "Homepage",
            "updated_at": "2026-08-08T00:00:00Z",
            "metadata": {"mime_type": "text/html"},
        }
    )

    assert asset.path == "connector/web-1"
    assert asset.name == "Homepage"
    assert asset.modified_at is not None
    assert asset.content_type == "text/html"


def test_local_file_connector_lists_and_reads_files(tmp_path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    first = docs / "a.txt"
    second = docs / "b.md"
    first.write_text("alpha", encoding="utf-8")
    second.write_text("beta", encoding="utf-8")
    connector = LocalFileConnector(tmp_path)

    assets = connector.list_assets("docs")
    file_assets = [asset for asset in assets if asset.entry_type == "file"]

    assert isinstance(connector, SourceConnectorPort)
    assert assets[0].path == "docs"
    assert assets[0].entry_type == "directory"
    assert [asset.path for asset in file_assets] == ["docs/a.txt", "docs/b.md"]
    assert file_assets[0].checksum.startswith("sha256:")
    assert connector.read_asset(file_assets[1]) == b"beta"
    assert connector.health()["status"] == "ok"


def test_local_file_connector_rejects_path_escape(tmp_path) -> None:
    connector = LocalFileConnector(tmp_path)

    with pytest.raises(ValueError, match="escapes"):
        connector.list_assets("../outside")


def test_github_repository_connector_lists_and_reads_assets(monkeypatch) -> None:
    def fake_request_json(self, path: str):
        assert self.health()["authenticated"] is True
        if path == "/repos/owner/repo/git/trees/main?recursive=1":
            return {
                "sha": "tree-sha",
                "tree": [
                    {"path": "docs/a.md", "type": "blob", "size": 5, "sha": "sha-a"},
                    {"path": "docs/skip.bin", "type": "blob", "size": 5, "sha": "sha-bin"},
                    {"path": "src/app.py", "type": "blob", "size": 5, "sha": "sha-py"},
                ],
            }
        if path == "/repos/owner/repo/contents/docs%2Fa.md?ref=main":
            return {"encoding": "base64", "content": "YWxwaGE=\n"}
        raise AssertionError(path)

    monkeypatch.setattr(GitHubRepositoryConnector, "_request_json", fake_request_json)
    connector = GitHubRepositoryConnector(access_token="token")

    assets = connector.list_assets("owner/repo@main:docs")
    file_assets = [asset for asset in assets if asset.entry_type == "file"]

    assert assets[0].path == "owner/repo@main:docs"
    assert assets[0].entry_type == "directory"
    assert [asset.path for asset in file_assets] == ["owner/repo@main:docs/a.md"]
    assert file_assets[0].checksum == "sha-a"
    assert connector.read_asset(file_assets[0]) == b"alpha"
