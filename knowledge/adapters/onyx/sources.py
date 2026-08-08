from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

from knowledge.ports import SourceAssetRef


class OnyxDocumentMapper:
    """Map Onyx connector document outputs into Knowledge source assets.

    The vendored Onyx connectors are copied under ``knowledge/third_party`` but
    many import the full upstream ``onyx.*`` runtime. This mapper intentionally
    works on document-like objects or dictionaries so Knowledge can adapt those
    outputs without leaking Onyx's database or pydantic models into the domain.
    """

    def to_asset_ref(self, document: Any, *, path_prefix: str = "onyx") -> SourceAssetRef:
        doc_id = str(_field(document, "id") or _field(document, "document_id") or "").strip()
        semantic_identifier = str(_field(document, "semantic_identifier") or "").strip()
        title = str(_field(document, "title") or "").strip()
        metadata = _field(document, "metadata") or {}
        doc_updated_at = _coerce_datetime(_field(document, "doc_updated_at") or _field(document, "updated_at"))
        name = semantic_identifier or title or doc_id or "onyx-document"
        safe_id = doc_id or _stable_digest(name)
        path = f"{path_prefix.rstrip('/')}/{safe_id.lstrip('/')}"
        checksum = _field(document, "checksum") or _call(document, "content_hash")
        content_type = _metadata_value(metadata, "content_type") or _metadata_value(metadata, "mime_type")

        return SourceAssetRef(
            path=path,
            name=name,
            entry_type="file",
            size=_coerce_int(_field(document, "size") or _metadata_value(metadata, "size")),
            checksum=str(checksum) if checksum else None,
            version=doc_updated_at.isoformat() if doc_updated_at else None,
            modified_at=doc_updated_at,
            content_type=str(content_type) if content_type else None,
        )


class OnyxLocalFileConnector:
    """Low-dependency local file connector shaped like an Onyx source adapter."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir).expanduser().resolve()

    def list_assets(self, root_path: str = ".") -> list[SourceAssetRef]:
        root = self._resolve_path(root_path)
        if not root.exists():
            return []
        if root.is_dir():
            return [self._asset_from_path(root)] + [
                self._asset_from_path(path)
                for path in sorted(root.rglob("*"))
                if path.is_file()
            ]
        files = [root]
        return [self._asset_from_path(path) for path in files]

    def read_asset(self, asset: SourceAssetRef) -> bytes:
        return self._resolve_path(asset.path).read_bytes()

    def health(self) -> dict:
        return {
            "status": "ok" if self.base_dir.exists() else "missing",
            "connector": "onyx_local_file",
            "base_dir": str(self.base_dir),
        }

    def _asset_from_path(self, path: Path) -> SourceAssetRef:
        stat = path.stat()
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        relative_path = path.relative_to(self.base_dir).as_posix()
        if path.is_dir():
            return SourceAssetRef(
                path=relative_path,
                name=path.name,
                entry_type="directory",
                size=None,
                checksum=None,
                version=str(stat.st_mtime_ns),
                modified_at=modified_at,
                content_type=None,
            )
        return SourceAssetRef(
            path=relative_path,
            name=path.name,
            entry_type="file",
            size=stat.st_size,
            checksum=f"sha256:{_sha256_file(path)}",
            version=str(stat.st_mtime_ns),
            modified_at=modified_at,
            content_type=None,
        )

    def _resolve_path(self, path: str) -> Path:
        candidate = (self.base_dir / path.lstrip("/")).resolve()
        if candidate != self.base_dir and self.base_dir not in candidate.parents:
            raise ValueError(f"path escapes connector root: {path}")
        return candidate


def _field(document: Any, name: str) -> Any:
    if isinstance(document, Mapping):
        return document.get(name)
    return getattr(document, name, None)


def _call(document: Any, name: str) -> Any:
    method = getattr(document, name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _metadata_value(metadata: Any, name: str) -> Any:
    if isinstance(metadata, Mapping):
        return metadata.get(name)
    return None


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
