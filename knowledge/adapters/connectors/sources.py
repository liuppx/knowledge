from __future__ import annotations

from collections.abc import Mapping
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from knowledge.ports import SourceAssetRef


class ConnectorDocumentMapper:
    """Map connector document-like outputs into Knowledge source assets."""

    def to_asset_ref(self, document: Any, *, path_prefix: str = "connector") -> SourceAssetRef:
        doc_id = str(_field(document, "id") or _field(document, "document_id") or "").strip()
        semantic_identifier = str(_field(document, "semantic_identifier") or "").strip()
        title = str(_field(document, "title") or "").strip()
        metadata = _field(document, "metadata") or {}
        doc_updated_at = _coerce_datetime(_field(document, "doc_updated_at") or _field(document, "updated_at"))
        name = semantic_identifier or title or doc_id or "connector-document"
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


class LocalFileConnector:
    """Low-dependency local file source connector."""

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
            "connector": "local_file",
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


class GitHubRepositoryConnector:
    """GitHub repository connector using a recursive-tree source scan.

    ``source_path`` accepts ``owner/repo``, ``owner/repo@branch``, or
    ``owner/repo@branch:path/prefix``. Asset paths are stored as
    ``owner/repo@branch:file/path`` so the evidence pipeline can read them back
    without carrying source-specific state.
    """

    max_file_size_bytes = 5 * 1024 * 1024

    def __init__(self, *, access_token: str = "", api_base_url: str = "https://api.github.com") -> None:
        self.access_token = access_token.strip()
        self.api_base_url = api_base_url.rstrip("/")

    def list_assets(self, root_path: str) -> list[SourceAssetRef]:
        spec = _parse_github_source_path(root_path)
        branch = spec["branch"] or self._default_branch(spec["owner"], spec["repo"])
        tree = self._request_json(
            f"/repos/{_quote_path(spec['owner'])}/{_quote_path(spec['repo'])}/git/trees/{_quote_path(branch)}?recursive=1"
        )
        prefix = spec["prefix"].strip("/")
        assets: list[SourceAssetRef] = []
        if prefix:
            assets.append(
                SourceAssetRef(
                    path=_format_github_asset_path(spec["owner"], spec["repo"], branch, prefix),
                    name=Path(prefix).name,
                    entry_type="directory",
                    version=str(tree.get("sha") or ""),
                )
            )
        for element in tree.get("tree", []):
            if not isinstance(element, Mapping) or element.get("type") != "blob":
                continue
            path = str(element.get("path") or "").strip("/")
            size = _coerce_int(element.get("size"))
            if not _is_indexable_github_path(path, size):
                continue
            if prefix and path != prefix and not path.startswith(f"{prefix}/"):
                continue
            assets.append(
                SourceAssetRef(
                    path=_format_github_asset_path(spec["owner"], spec["repo"], branch, path),
                    name=Path(path).name,
                    entry_type="file",
                    size=size,
                    checksum=str(element.get("sha") or "") or None,
                    version=str(element.get("sha") or "") or None,
                    content_type=None,
                )
            )
        return assets

    def read_asset(self, asset: SourceAssetRef) -> bytes:
        spec = _parse_github_asset_path(asset.path)
        payload = self._request_json(
            f"/repos/{_quote_path(spec['owner'])}/{_quote_path(spec['repo'])}/contents/{_quote_path(spec['path'])}?ref={_quote_path(spec['branch'])}"
        )
        if isinstance(payload, list):
            raise ValueError(f"expected GitHub file asset, got directory: {asset.path}")
        encoded = str(payload.get("content") or "")
        encoding = str(payload.get("encoding") or "").lower()
        if encoding != "base64":
            raise ValueError(f"unsupported GitHub content encoding: {encoding}")
        return base64.b64decode(encoded.replace("\n", ""))

    def health(self) -> dict:
        return {
            "status": "ok",
            "connector": "github_repository",
            "api_base_url": self.api_base_url,
            "authenticated": bool(self.access_token),
        }

    def _default_branch(self, owner: str, repo: str) -> str:
        payload = self._request_json(f"/repos/{_quote_path(owner)}/{_quote_path(repo)}")
        branch = str(payload.get("default_branch") or "").strip()
        if not branch:
            raise ValueError(f"GitHub repository default_branch missing: {owner}/{repo}")
        return branch

    def _request_json(self, path: str) -> Any:
        request = Request(f"{self.api_base_url}{path}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "knowledge-github-source-connector")
        if self.access_token:
            request.add_header("Authorization", f"Bearer {self.access_token}")
        with urlopen(request, timeout=30) as response:  # noqa: S310 - user-configured GitHub API endpoint
            return json.loads(response.read().decode("utf-8"))


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


def _parse_github_source_path(source_path: str) -> dict[str, str]:
    raw = str(source_path or "").strip().removeprefix("https://github.com/").strip("/")
    repo_part, _, prefix = raw.partition(":")
    owner_repo, _, branch = repo_part.partition("@")
    parts = owner_repo.split("/", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError("GitHub source_path must be owner/repo, owner/repo@branch, or owner/repo@branch:path")
    return {
        "owner": parts[0],
        "repo": parts[1],
        "branch": branch,
        "prefix": prefix or (parts[2] if len(parts) > 2 else ""),
    }


def _parse_github_asset_path(asset_path: str) -> dict[str, str]:
    spec = _parse_github_source_path(asset_path)
    if not spec["branch"] or not spec["prefix"]:
        raise ValueError(f"invalid GitHub asset path: {asset_path}")
    return {"owner": spec["owner"], "repo": spec["repo"], "branch": spec["branch"], "path": spec["prefix"]}


def _format_github_asset_path(owner: str, repo: str, branch: str, path: str) -> str:
    return f"{owner}/{repo}@{branch}:{path.strip('/')}"


def _quote_path(value: str) -> str:
    return quote(value, safe="")


def _is_indexable_github_path(path: str, size: int | None) -> bool:
    if not path or path.endswith("/"):
        return False
    if size is not None and size > GitHubRepositoryConnector.max_file_size_bytes:
        return False
    suffix = Path(path).suffix.lower()
    return suffix in {
        ".csv",
        ".html",
        ".htm",
        ".json",
        ".log",
        ".md",
        ".rst",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
