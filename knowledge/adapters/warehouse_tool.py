from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from knowledge.ports.storage import AssetAccessContext, AssetEntry, AssetReference, AssetStoreError


@dataclass(frozen=True)
class WarehouseToolAuthorization:
    """Bearer credential supplied by the caller's secure credential resolver."""

    token: str = field(repr=False)


class WarehouseToolAssetStore:
    """AssetStorePort adapter for Warehouse's published HTTP Tool contract."""

    CALL_PATH = "/api/v1/public/tools/warehouse/call"
    MAX_READ_BYTES = 5 * 1024 * 1024
    MAX_WRITE_BYTES = 5 * 1024 * 1024

    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(30.0, read=60.0, write=30.0))

    def list(self, context: AssetAccessContext, prefix: str) -> list[AssetEntry]:
        result = self._call(context, "warehouse.object.list", {"prefix": prefix, "delimiter": "/"})
        entries = [self._entry(row, "file") for row in result.get("objects", [])]
        entries.extend(
            AssetEntry(
                reference=AssetReference(provider="warehouse", object_id=str(path)),
                name=str(path).rstrip("/").rsplit("/", 1)[-1],
                entry_type="directory",
            )
            for path in result.get("prefixes", [])
        )
        return entries

    def stat(self, context: AssetAccessContext, reference: AssetReference | str) -> AssetReference:
        path = self._path(reference)
        result = self._call(context, "warehouse.object.stat", {"path": path})
        return self._reference(result)

    def read(self, context: AssetAccessContext, reference: AssetReference | str) -> bytes:
        path = self._path(reference)
        result = self._call(
            context,
            "warehouse.object.read",
            {"path": path, "mode": "content", "maxBytes": self.MAX_READ_BYTES},
        )
        content = str(result.get("content") or "")
        encoding = result.get("encoding")
        if encoding == "utf-8":
            payload = content.encode("utf-8")
        elif encoding == "base64":
            try:
                payload = base64.b64decode(content, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise AssetStoreError("upstream_error", "Warehouse Tool returned invalid base64 content") from exc
        else:
            raise AssetStoreError("upstream_error", "Warehouse Tool returned an unsupported content encoding")
        metadata = result.get("metadata") or {}
        if result.get("truncated") is True or len(payload) > self.MAX_READ_BYTES:
            raise AssetStoreError("too_large", "Warehouse Tool returned content beyond the supported limit")
        expected = str(metadata.get("checksumSha256") or "").lower()
        if expected and hashlib.sha256(payload).hexdigest() != expected:
            raise AssetStoreError("integrity_error", "asset checksum does not match Warehouse metadata")
        return payload

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
        if len(content) > self.MAX_WRITE_BYTES:
            raise AssetStoreError("too_large", "Warehouse Tool writes are limited to 5 MiB")
        name = str(file_name or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
        if not name or name in {".", ".."}:
            raise AssetStoreError("invalid_request", "asset file name is invalid")
        path = f"{target_dir.rstrip('/')}/{name}"
        try:
            content.decode("utf-8")
            encoded = content.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoded = base64.b64encode(content).decode("ascii")
            encoding = "base64"
        arguments: dict[str, object] = {
            "path": path,
            "content": encoded,
            "encoding": encoding,
            "contentType": content_type or "application/octet-stream",
            "checksumSha256": hashlib.sha256(content).hexdigest(),
            "overwrite": overwrite,
        }
        if if_match:
            arguments["ifMatch"] = if_match
        result = self._call(context, "warehouse.object.put", arguments)
        return self._reference(result)

    def _call(self, context: AssetAccessContext, name: str, arguments: dict[str, object]) -> dict:
        token = self._token(context)
        try:
            response = self.client.post(
                f"{self.base_url}{self.CALL_PATH}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "name": name,
                    "arguments": arguments,
                    **({"traceId": context.trace_id} if context.trace_id else {}),
                },
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AssetStoreError("unavailable") from exc
        if not response.is_success:
            try:
                body = response.json()
            except ValueError:
                body = {}
            code = self._error_code(response.status_code, body.get("code") if isinstance(body, dict) else None)
            raise AssetStoreError(code)
        try:
            payload = response.json()
            result = payload["result"]
        except (ValueError, KeyError, TypeError) as exc:
            raise AssetStoreError("upstream_error", "Warehouse Tool returned an invalid response") from exc
        if not isinstance(result, dict):
            raise AssetStoreError("upstream_error", "Warehouse Tool returned an invalid result")
        return result

    @staticmethod
    def _token(context: AssetAccessContext) -> str:
        authorization = context.authorization
        if not isinstance(authorization, WarehouseToolAuthorization) or not authorization.token.strip():
            raise AssetStoreError("invalid_request", "Warehouse Tool authorization is missing")
        return authorization.token

    @classmethod
    def _entry(cls, payload: dict, entry_type: str) -> AssetEntry:
        reference = cls._reference(payload)
        path = reference.object_id.rstrip("/")
        return AssetEntry(reference=reference, name=path.rsplit("/", 1)[-1], entry_type=entry_type)

    @staticmethod
    def _reference(payload: dict) -> AssetReference:
        modified = payload.get("modifiedAt")
        try:
            modified_at = datetime.fromisoformat(str(modified).replace("Z", "+00:00")) if modified else None
        except ValueError:
            modified_at = None
        return AssetReference(
            provider="warehouse",
            object_id=str(payload.get("path") or ""),
            etag=str(payload.get("etag") or "") or None,
            sha256=str(payload.get("checksumSha256") or "") or None,
            size=int(payload["size"]) if payload.get("size") is not None else None,
            content_type=str(payload.get("contentType") or "") or None,
            modified_at=modified_at,
        )

    @staticmethod
    def _path(reference: AssetReference | str) -> str:
        return reference.object_id if isinstance(reference, AssetReference) else str(reference)

    @staticmethod
    def _error_code(status: int, upstream_code: object) -> str:
        code = str(upstream_code or "").upper()
        mapped = {
            "OBJECT_NOT_FOUND": "not_found",
            "NOT_FOUND": "not_found",
            "PERMISSION_DENIED": "permission_denied",
            "FORBIDDEN": "permission_denied",
            "OBJECT_EXISTS": "conflict",
            "PRECONDITION_FAILED": "version_conflict",
            "CONTENT_TOO_LARGE": "too_large",
            "QUOTA_EXCEEDED": "quota_or_rate_limited",
            "RATE_LIMITED": "quota_or_rate_limited",
            "STORAGE_UNAVAILABLE": "unavailable",
            "INVALID_PATH": "invalid_request",
        }
        if code in mapped:
            return mapped[code]
        return {
            401: "permission_denied",
            403: "permission_denied",
            404: "not_found",
            409: "conflict",
            412: "version_conflict",
            413: "too_large",
            429: "quota_or_rate_limited",
        }.get(status, "unavailable" if status >= 500 else "upstream_error")
