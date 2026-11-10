from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

import httpx

from knowledge.ports.storage import AssetAccessContext, AssetEntry, AssetReference, AssetStoreError
from knowledge.adapters.warehouse_tool import WarehouseToolAssetStore, WarehouseToolAuthorization
from knowledge.services.warehouse import WarehouseGateway, WarehouseRequestAuth
from knowledge.core.settings import get_settings


class LegacyWarehouseAssetStore:
    """AssetStorePort adapter over the current S3/WebDAV Warehouse gateway.

    This is a compatibility adapter. Callers resolve authorization through
    Knowledge first; the adapter owns the transport-specific gateway calls.
    """

    def __init__(self, gateway: WarehouseGateway) -> None:
        self.gateway = gateway

    def list(self, context: AssetAccessContext, prefix: str) -> list[AssetEntry]:
        try:
            rows = self.gateway.browse(context.owner_id, prefix, auth=self._auth(context))
        except Exception as exc:  # noqa: BLE001 - normalize adapter failures
            raise self._translate(exc) from exc
        return [
            AssetEntry(
                reference=AssetReference(provider="warehouse", object_id=row.path, size=row.size, modified_at=row.modified_at),
                name=row.name,
                entry_type=row.entry_type,
            )
            for row in rows
        ]

    def stat(self, context: AssetAccessContext, reference: AssetReference | str) -> AssetReference:
        object_id = reference.object_id if isinstance(reference, AssetReference) else str(reference)
        parent, _, _ = object_id.rstrip("/").rpartition("/")
        for entry in self.list(context, parent or "/"):
            if entry.reference.object_id.rstrip("/") == object_id.rstrip("/"):
                return entry.reference
        raise AssetStoreError("not_found")

    def read(self, context: AssetAccessContext, reference: AssetReference | str) -> bytes:
        object_id = reference.object_id if isinstance(reference, AssetReference) else str(reference)
        try:
            return self.gateway.read_file(
                context.owner_id,
                object_id,
                auth=self._auth(context),
            )
        except Exception as exc:  # noqa: BLE001 - normalize adapter failures
            raise self._translate(exc) from exc

    def write(
        self,
        context: AssetAccessContext,
        target_dir: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
        *,
        overwrite: bool = False,
        if_match: str | None = None,
    ) -> AssetReference:
        if if_match is not None:
            raise AssetStoreError(
                "invalid_request",
                "conditional writes are not supported by the legacy Warehouse gateway",
            )
        safe_name = PurePosixPath(str(file_name or "")).name
        if not safe_name or safe_name in {".", ".."}:
            raise AssetStoreError("invalid_request", "asset file name is invalid")
        try:
            self.gateway.ensure_app_space(
                context.owner_id,
                auth=self._auth(context),
                base_path=context.credential_root,
                target_path=target_dir,
            )
            path = self.gateway.upload_file(
                context.owner_id,
                target_dir,
                safe_name,
                content,
                auth=self._auth(context),
                content_type=content_type,
            )
        except Exception as exc:  # noqa: BLE001 - normalize adapter failures
            raise self._translate(exc) from exc
        return AssetReference(
            provider="warehouse",
            object_id=path,
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
            content_type=content_type,
        )

    @staticmethod
    def _auth(context: AssetAccessContext) -> WarehouseRequestAuth:
        if not isinstance(context.authorization, WarehouseRequestAuth):
            raise AssetStoreError("invalid_request", "asset authorization context is invalid")
        return context.authorization

    @staticmethod
    def _translate(exc: Exception) -> AssetStoreError:
        if isinstance(exc, AssetStoreError):
            return exc
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            code = {
                401: "permission_denied",
                403: "permission_denied",
                404: "not_found",
                409: "conflict",
                412: "version_conflict",
                413: "too_large",
                429: "quota_or_rate_limited",
            }.get(status, "unavailable" if status >= 500 else "upstream_error")
            return AssetStoreError(code)
        if isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.NetworkError, OSError)):
            return AssetStoreError("unavailable")
        if isinstance(exc, ValueError):
            return AssetStoreError("invalid_request")
        return AssetStoreError("upstream_error")


class AdaptiveWarehouseAssetStore:
    """Use the scoped HTTP Tool credential when available, retaining legacy large-file access."""

    def __init__(self, legacy: LegacyWarehouseAssetStore, tool: WarehouseToolAssetStore) -> None:
        self.legacy = legacy
        self.tool = tool

    def list(self, context: AssetAccessContext, prefix: str) -> list[AssetEntry]:
        return self._store(context).list(context, prefix)

    def stat(self, context: AssetAccessContext, reference: AssetReference | str) -> AssetReference:
        return self._store(context).stat(context, reference)

    def read(self, context: AssetAccessContext, reference: AssetReference | str) -> bytes:
        store = self._store(context)
        if store is self.tool:
            try:
                return store.read(context, reference)
            except AssetStoreError as exc:
                if exc.code != "too_large" or context.fallback_authorization is None:
                    raise
                return self.legacy.read(self._legacy_context(context), reference)
        return store.read(context, reference)

    def write(self, context: AssetAccessContext, target_dir: str, file_name: str, content: bytes, content_type: str | None = None, *, overwrite: bool = False, if_match: str | None = None) -> AssetReference:
        store = self._store(context)
        if store is self.tool:
            try:
                return store.write(context, target_dir, file_name, content, content_type, overwrite=overwrite, if_match=if_match)
            except AssetStoreError as exc:
                if exc.code != "too_large" or context.fallback_authorization is None:
                    raise
                return self.legacy.write(self._legacy_context(context), target_dir, file_name, content, content_type, overwrite=overwrite, if_match=if_match)
        return store.write(context, target_dir, file_name, content, content_type, overwrite=overwrite, if_match=if_match)

    def _store(self, context: AssetAccessContext):
        return self.tool if isinstance(context.authorization, WarehouseToolAuthorization) else self.legacy

    @staticmethod
    def _legacy_context(context: AssetAccessContext) -> AssetAccessContext:
        return AssetAccessContext(
            owner_id=context.owner_id,
            authorization=context.fallback_authorization,
            credential_root=context.credential_root,
            trace_id=context.trace_id,
        )


def build_warehouse_asset_store(gateway: WarehouseGateway) -> AdaptiveWarehouseAssetStore:
    settings = get_settings()
    base_url = settings.warehouse_api_base_url or settings.warehouse_base_url
    return AdaptiveWarehouseAssetStore(
        LegacyWarehouseAssetStore(gateway),
        WarehouseToolAssetStore(base_url),
    )
