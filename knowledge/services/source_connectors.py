from __future__ import annotations

from knowledge.adapters.onyx import OnyxLocalFileConnector
from knowledge.core.settings import get_settings
from knowledge.ports import SourceConnectorPort


def build_source_connector() -> SourceConnectorPort | None:
    settings = get_settings()
    mode = settings.source_connector_mode.lower()
    if mode == "warehouse":
        return None
    if mode == "onyx_local_file":
        return OnyxLocalFileConnector(settings.onyx_local_file_root)
    raise ValueError(f"unsupported SOURCE_CONNECTOR_MODE: {settings.source_connector_mode}")
