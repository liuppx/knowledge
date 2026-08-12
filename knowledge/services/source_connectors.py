from __future__ import annotations

from knowledge.adapters.connectors import GitHubRepositoryConnector, LocalFileConnector
from knowledge.core.settings import Settings, get_settings
from knowledge.ports import SourceConnectorPort


def build_source_connector() -> SourceConnectorPort | None:
    settings = get_settings()
    mode = settings.source_connector_mode.lower()
    return build_source_connector_for_type(mode, settings=settings, label="SOURCE_CONNECTOR_MODE")


def build_source_connector_for_type(
    source_type: str,
    *,
    settings: Settings | None = None,
    label: str = "source_type",
) -> SourceConnectorPort | None:
    current_settings = settings or get_settings()
    mode = str(source_type or "warehouse").strip().lower() or "warehouse"
    if mode == "warehouse":
        return None
    if mode == "local_file":
        return LocalFileConnector(current_settings.local_file_connector_root)
    if mode == "github_repository":
        return GitHubRepositoryConnector(
            access_token=current_settings.github_connector_access_token,
            api_base_url=current_settings.github_connector_api_base_url,
        )
    raise ValueError(f"unsupported {label}: {source_type}")
