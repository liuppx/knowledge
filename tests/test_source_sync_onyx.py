from __future__ import annotations

from sqlalchemy import select

from knowledge.core.settings import get_settings
from knowledge.db.base import Base
from knowledge.db.schema import ensure_runtime_schema
from knowledge.db.session import engine, session_scope
from knowledge.models import KnowledgeBase, SourceAsset, WalletUser
from knowledge.services.asset_inventory import AssetInventoryService
from knowledge.services.warehouse_scope import warehouse_app_path
from knowledge.services.source_registry import SourceRegistryService
from knowledge.services.source_sync import SourceSyncService


def _ensure_schema_ready() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)


def test_source_sync_discovers_onyx_local_file_assets(monkeypatch, tmp_path) -> None:
    docs = tmp_path / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    (docs / "a.txt").write_text("alpha", encoding="utf-8")
    (nested / "b.md").write_text("beta", encoding="utf-8")

    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "onyx_local_file")
    monkeypatch.setenv("ONYX_LOCAL_FILE_ROOT", str(tmp_path))
    get_settings.cache_clear()
    _ensure_schema_ready()

    wallet_address = "wallet-onyx-source-sync"
    try:
        with session_scope() as db:
            user = db.get(WalletUser, wallet_address) or WalletUser(wallet_address=wallet_address)
            db.add(user)
            kb = KnowledgeBase(owner_wallet_address=wallet_address, name="Onyx Source KB", description="onyx")
            db.add(kb)
            db.flush()

            registry = SourceRegistryService()
            source = registry.create_source(
                db,
                wallet_address,
                kb.id,
                source_type="onyx_local_file",
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

            assert synced_source.source_type == "onyx_local_file"
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
    finally:
        get_settings.cache_clear()


def test_warehouse_source_type_does_not_use_onyx_connector(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "onyx_local_file")
    monkeypatch.setenv("ONYX_LOCAL_FILE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        inventory = AssetInventoryService()

        assert inventory._connector_for_source_type("warehouse") is None
        assert inventory._connector_for_source_type("onyx_local_file") is not None
        assert inventory._connector_for_source_type(warehouse_app_path("library")) is None
    finally:
        get_settings.cache_clear()
