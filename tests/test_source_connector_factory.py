from __future__ import annotations

import pytest

from knowledge.adapters.onyx import OnyxLocalFileConnector
from knowledge.core.settings import get_settings
from knowledge.services.source_connectors import build_source_connector


def test_source_connector_factory_defaults_to_warehouse(monkeypatch) -> None:
    monkeypatch.delenv("SOURCE_CONNECTOR_MODE", raising=False)
    get_settings.cache_clear()

    assert build_source_connector() is None


def test_source_connector_factory_can_select_onyx_local_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "onyx_local_file")
    monkeypatch.setenv("ONYX_LOCAL_FILE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    connector = build_source_connector()

    assert isinstance(connector, OnyxLocalFileConnector)
    assert connector.health()["base_dir"] == str(tmp_path.resolve())


def test_source_connector_factory_rejects_unknown_mode(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "unknown")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="unsupported"):
        build_source_connector()
