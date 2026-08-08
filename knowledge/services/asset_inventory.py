from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import logging

from sqlalchemy.orm import Session

from knowledge.core.settings import get_settings
from knowledge.adapters.onyx import OnyxLocalFileConnector
from knowledge.ports import SourceAssetRef, SourceConnectorPort
from knowledge.services.filetypes import infer_file_type
from knowledge.services.source_connectors import build_source_connector
from knowledge.services.warehouse import WarehouseFileEntry, WarehouseGateway, build_warehouse_gateway
from knowledge.services.warehouse_access import ResolvedWarehouseAccess, WarehouseAccessService
from knowledge.services.warehouse_scope import ensure_current_app_path, normalize_warehouse_path, warehouse_app_root


class SourcePathMissingError(Exception):
    pass


class SourceScopeMismatchError(Exception):
    pass


@dataclass
class AssetSnapshot:
    asset_path: str
    asset_name: str
    asset_type: str
    source_version: str


class AssetInventoryService:
    def __init__(
        self,
        warehouse_gateway: WarehouseGateway | None = None,
        warehouse_access_service: WarehouseAccessService | None = None,
    ) -> None:
        self.settings = get_settings()
        self.warehouse_gateway = warehouse_gateway or build_warehouse_gateway()
        self.warehouse_access_service = warehouse_access_service or WarehouseAccessService(warehouse_gateway=self.warehouse_gateway)
        self.source_connector = build_source_connector()
        self.logger = logging.getLogger(__name__)

    def list_asset_snapshots(
        self,
        db: Session,
        wallet_address: str,
        source_path: str,
        scope_type: str,
        kb_id: int | None = None,
        source_type: str = "warehouse",
    ) -> list[AssetSnapshot]:
        connector = self._connector_for_source_type(source_type)
        if connector is not None:
            return self._list_connector_asset_snapshots(connector, source_path, scope_type)

        normalized_source_path = ensure_current_app_path(source_path, "source_path", self.settings)
        normalized_scope_type = str(scope_type or "directory").strip().lower() or "directory"
        exists, entry_type = self.path_exists(db, wallet_address, normalized_source_path, kb_id=kb_id)
        if not exists:
            raise SourcePathMissingError(normalized_source_path)
        if normalized_scope_type == "file" and entry_type != "file":
            raise SourceScopeMismatchError(f"source path {normalized_source_path} is not a file")
        if normalized_scope_type == "directory" and entry_type != "directory":
            raise SourceScopeMismatchError(f"source path {normalized_source_path} is not a directory")

        if normalized_scope_type == "file":
            file_entry = self._get_exact_entry(db, wallet_address, normalized_source_path, kb_id=kb_id)
            if file_entry is None or file_entry.entry_type != "file":
                raise SourcePathMissingError(normalized_source_path)
            return [self._snapshot_for_entry(file_entry)]

        entries = self._iter_files(db, wallet_address, normalized_source_path, kb_id=kb_id)
        return [self._snapshot_for_entry(entry) for entry in entries]

    def path_exists(
        self,
        db: Session,
        wallet_address: str,
        path: str,
        kb_id: int | None = None,
        source_type: str = "warehouse",
    ) -> tuple[bool, str | None]:
        connector = self._connector_for_source_type(source_type)
        if connector is not None:
            assets = connector.list_assets(path)
            if not assets:
                return False, None
            if len(assets) == 1 and assets[0].path == path:
                return True, assets[0].entry_type
            return True, "directory"

        normalized_path = ensure_current_app_path(path, "path", self.settings)
        app_root = warehouse_app_root(self.settings)
        if kb_id is None:
            resolved = self.warehouse_access_service.resolve_write_access(db, wallet_address, normalized_path)
        else:
            resolved = self.warehouse_access_service.resolve_path_read_access(
                db,
                wallet_address,
                kb_id,
                normalized_path,
                allow_write_fallback=True,
            )
        if normalized_path == app_root and self.settings.warehouse_gateway_mode == "mock":
            return True, "directory"
        entry = self._get_exact_entry(db, wallet_address, normalized_path, kb_id=kb_id, resolved=resolved)
        if entry is None:
            return False, None
        return True, entry.entry_type

    def _iter_files(self, db: Session, wallet_address: str, source_path: str, kb_id: int | None = None) -> list[WarehouseFileEntry]:
        resolved = self._resolve_read_access(db, wallet_address, source_path, kb_id=kb_id)
        entries = self._browse_with_resolved_access(db, wallet_address, source_path, resolved)
        if len(entries) == 1 and entries[0].path == source_path and entries[0].entry_type == "file":
            return entries
        files: list[WarehouseFileEntry] = []
        for entry in entries:
            if entry.entry_type == "file":
                files.append(entry)
                continue
            if entry.entry_type == "directory":
                files.extend(self._iter_files(db, wallet_address, entry.path, kb_id=kb_id))
        return files

    def _get_exact_entry(
        self,
        db: Session,
        wallet_address: str,
        path: str,
        kb_id: int | None = None,
        resolved: ResolvedWarehouseAccess | None = None,
    ) -> WarehouseFileEntry | None:
        normalized_path = normalize_warehouse_path(path)
        parent = self._parent_path(normalized_path)
        read_access = resolved or self._resolve_read_access(db, wallet_address, parent, kb_id=kb_id)
        entries = self._browse_with_resolved_access(db, wallet_address, parent, read_access)
        for entry in entries:
            if normalize_warehouse_path(entry.path) == normalized_path:
                return entry
        if parent == normalized_path:
            root_entries = self._browse_with_resolved_access(db, wallet_address, normalized_path, read_access)
            for entry in root_entries:
                if normalize_warehouse_path(entry.path) == normalized_path:
                    return entry
        return None

    def _resolve_read_access(
        self,
        db: Session,
        wallet_address: str,
        path: str,
        kb_id: int | None = None,
    ) -> ResolvedWarehouseAccess:
        normalized_path = ensure_current_app_path(path, "path", self.settings)
        if kb_id is None:
            return self.warehouse_access_service.resolve_write_access(db, wallet_address, normalized_path)
        return self.warehouse_access_service.resolve_path_read_access(
            db,
            wallet_address,
            kb_id,
            normalized_path,
            allow_write_fallback=True,
        )

    def _browse_with_resolved_access(
        self,
        db: Session,
        wallet_address: str,
        path: str,
        resolved: ResolvedWarehouseAccess,
    ) -> list[WarehouseFileEntry]:
        try:
            entries = self.warehouse_gateway.browse(wallet_address, path, auth=resolved.auth)
            self.warehouse_access_service.mark_access_success(resolved)
            return entries
        except Exception as exc:  # noqa: BLE001
            if self.warehouse_access_service.is_auth_error(exc):
                self.logger.warning(
                    "warehouse browse auth failed during asset inventory",
                    extra={
                        "wallet_address": wallet_address,
                        "path": path,
                        "credential_id": resolved.credential.id,
                        "credential_kind": resolved.credential.credential_kind,
                    },
                )
                self.warehouse_access_service.mark_access_invalid(resolved)
                db.commit()
            raise

    @staticmethod
    def _snapshot_for_entry(entry: WarehouseFileEntry) -> AssetSnapshot:
        return AssetSnapshot(
            asset_path=normalize_warehouse_path(entry.path),
            asset_name=entry.name,
            asset_type=infer_file_type(entry.name),
            source_version=entry.modified_at.isoformat() if entry.modified_at else "",
        )

    def _connector_for_source_type(self, source_type: str) -> SourceConnectorPort | None:
        normalized_source_type = str(source_type or "warehouse").strip().lower()
        if normalized_source_type == "warehouse":
            return None
        if normalized_source_type == "onyx_local_file":
            if isinstance(self.source_connector, OnyxLocalFileConnector):
                return self.source_connector
            return OnyxLocalFileConnector(self.settings.onyx_local_file_root)
        return None

    def _list_connector_asset_snapshots(
        self,
        connector: SourceConnectorPort,
        source_path: str,
        scope_type: str,
    ) -> list[AssetSnapshot]:
        normalized_scope_type = str(scope_type or "directory").strip().lower() or "directory"
        assets = list(connector.list_assets(source_path))
        if not assets:
            raise SourcePathMissingError(source_path)
        if normalized_scope_type == "file" and len(assets) != 1:
            raise SourceScopeMismatchError(f"source path {source_path} is not a file")
        if normalized_scope_type == "directory" and len(assets) == 1 and assets[0].path == source_path and assets[0].entry_type != "directory":
            raise SourceScopeMismatchError(f"source path {source_path} is not a directory")
        return [self._snapshot_for_asset_ref(asset) for asset in assets if asset.entry_type == "file"]

    @staticmethod
    def _snapshot_for_asset_ref(asset: SourceAssetRef) -> AssetSnapshot:
        return AssetSnapshot(
            asset_path=asset.path,
            asset_name=asset.name,
            asset_type=infer_file_type(asset.name),
            source_version=asset.version or asset.checksum or (asset.modified_at.isoformat() if asset.modified_at else ""),
        )

    @staticmethod
    def _parent_path(path: str) -> str:
        normalized_path = normalize_warehouse_path(path)
        parent = str(PurePosixPath(normalized_path).parent)
        if parent == ".":
            return normalized_path
        return normalize_warehouse_path(parent)
