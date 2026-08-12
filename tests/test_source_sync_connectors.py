from __future__ import annotations

import pytest
from sqlalchemy import select

from knowledge.core.settings import get_settings
from knowledge.db.base import Base
from knowledge.db.schema import ensure_runtime_schema
from knowledge.db.session import engine, session_scope
from knowledge.models import EvidenceUnit, KnowledgeBase, SourceAsset, WalletUser
from knowledge.adapters.connectors import GitHubRepositoryConnector
from knowledge.services.asset_inventory import AssetInventoryService
from knowledge.services.evidence_pipeline import EvidencePipelineService
from knowledge.services.source_registry import SourceRegistryService
from knowledge.services.source_sync import SourceSyncService


def _ensure_schema_ready() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)


def test_source_sync_discovers_local_file_assets(monkeypatch, tmp_path) -> None:
    docs = tmp_path / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    (docs / "a.txt").write_text("alpha", encoding="utf-8")
    (nested / "b.md").write_text("beta", encoding="utf-8")

    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "local_file")
    monkeypatch.setenv("LOCAL_FILE_CONNECTOR_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _ensure_schema_ready()

    wallet_address = "wallet-source-sync"
    try:
        with session_scope() as db:
            user = db.get(WalletUser, wallet_address) or WalletUser(wallet_address=wallet_address)
            db.add(user)
            kb = KnowledgeBase(owner_wallet_address=wallet_address, name="Local File Source KB", description="local-file")
            db.add(kb)
            db.flush()

            registry = SourceRegistryService()
            source = registry.create_source(
                db,
                wallet_address,
                kb.id,
                source_type="local_file",
                source_path="docs",
                scope_type="directory",
                enabled=True,
                missing_policy="mark_missing",
            )

            sync = SourceSyncService(
                source_registry_service=registry,
                asset_inventory_service=AssetInventoryService(),
            )
            synced_source, stats = sync.scan_source(db, wallet_address, kb.id, source.id)

            assert synced_source.source_type == "local_file"
            assert synced_source.sync_status == "synced"
            assert stats.total_assets == 2
            assert stats.discovered_assets == 2

            assets = list(
                db.scalars(
                    select(SourceAsset)
                    .where(SourceAsset.source_id == source.id)
                    .order_by(SourceAsset.asset_path.asc())
                ).all()
            )
            assert [asset.asset_path for asset in assets] == ["docs/a.txt", "docs/nested/b.md"]
            assert [asset.asset_name for asset in assets] == ["a.txt", "b.md"]
            assert all(asset.source_version for asset in assets)
            assert all(asset.availability_status == "discovered" for asset in assets)

            evidence_stats = EvidencePipelineService().build_for_source(db, wallet_address, kb.id, source.id)
            assert evidence_stats.processed_asset_count == 2
            assert evidence_stats.built_evidence_count == 2

            evidence_units = list(
                db.scalars(
                    select(EvidenceUnit)
                    .join(SourceAsset, SourceAsset.id == EvidenceUnit.asset_id)
                    .where(SourceAsset.source_id == source.id)
                    .order_by(EvidenceUnit.id.asc())
                ).all()
            )
            assert [unit.text for unit in evidence_units] == ["alpha", "beta"]
            assert all(unit.vector_status == "indexed" for unit in evidence_units)
    finally:
        get_settings.cache_clear()


def test_warehouse_source_type_does_not_use_external_connector(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "local_file")
    monkeypatch.setenv("LOCAL_FILE_CONNECTOR_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        inventory = AssetInventoryService()

        assert inventory._connector_for_source_type("warehouse") is None
        assert inventory._connector_for_source_type("local_file") is not None
        with pytest.raises(ValueError, match="unsupported source_type"):
            inventory._connector_for_source_type("unknown")
    finally:
        get_settings.cache_clear()


def test_source_sync_builds_evidence_from_github_repository(monkeypatch) -> None:
    def fake_request_json(self, path: str):
        if path == "/repos/owner/repo/git/trees/main?recursive=1":
            return {
                "sha": "tree-sha",
                "tree": [
                    {"path": "docs/a.md", "type": "blob", "size": 18, "sha": "sha-a"},
                    {"path": "docs/b.txt", "type": "blob", "size": 17, "sha": "sha-b"},
                    {"path": "assets/logo.png", "type": "blob", "size": 12, "sha": "sha-png"},
                ],
            }
        if path == "/repos/owner/repo/contents/docs%2Fa.md?ref=main":
            return {"encoding": "base64", "content": "IyBBbHBoYVxuR2l0SHViIGRvYyBB"}
        if path == "/repos/owner/repo/contents/docs%2Fb.txt?ref=main":
            return {"encoding": "base64", "content": "R2l0SHViIGRvYyBC"}
        raise AssertionError(path)

    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "github_repository")
    monkeypatch.setenv("GITHUB_CONNECTOR_ACCESS_TOKEN", "token")
    monkeypatch.setattr(GitHubRepositoryConnector, "_request_json", fake_request_json)
    get_settings.cache_clear()
    _ensure_schema_ready()

    wallet_address = "wallet-github-source-sync"
    try:
        with session_scope() as db:
            user = db.get(WalletUser, wallet_address) or WalletUser(wallet_address=wallet_address)
            db.add(user)
            kb = KnowledgeBase(owner_wallet_address=wallet_address, name="GitHub Source KB", description="github")
            db.add(kb)
            db.flush()

            registry = SourceRegistryService()
            source = registry.create_source(
                db,
                wallet_address,
                kb.id,
                source_type="github_repository",
                source_path="owner/repo@main:docs",
                scope_type="directory",
                enabled=True,
                missing_policy="mark_missing",
            )

            synced_source, stats = SourceSyncService(
                source_registry_service=registry,
                asset_inventory_service=AssetInventoryService(),
            ).scan_source(db, wallet_address, kb.id, source.id)

            assert synced_source.sync_status == "synced"
            assert stats.discovered_assets == 2
            assets = list(
                db.scalars(
                    select(SourceAsset)
                    .where(SourceAsset.source_id == source.id)
                    .order_by(SourceAsset.asset_path.asc())
                ).all()
            )
            assert [asset.asset_path for asset in assets] == [
                "owner/repo@main:docs/a.md",
                "owner/repo@main:docs/b.txt",
            ]
            assert [asset.source_version for asset in assets] == ["sha-a", "sha-b"]

            evidence_stats = EvidencePipelineService().build_for_source(db, wallet_address, kb.id, source.id)
            assert evidence_stats.processed_asset_count == 2
            assert evidence_stats.built_evidence_count == 2
            evidence_text = "\n".join(
                db.scalars(
                    select(EvidenceUnit.text)
                    .join(SourceAsset, SourceAsset.id == EvidenceUnit.asset_id)
                    .where(SourceAsset.source_id == source.id)
                    .order_by(EvidenceUnit.id.asc())
                ).all()
            )
            assert "Alpha" in evidence_text
            assert "GitHub doc B" in evidence_text
    finally:
        get_settings.cache_clear()
