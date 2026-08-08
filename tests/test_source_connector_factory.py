from __future__ import annotations

import pytest

from knowledge.adapters.connectors import GitHubRepositoryConnector, LocalFileConnector
from knowledge.core.settings import get_settings
from knowledge.services.source_connectors import build_source_connector, build_source_connector_for_type


def test_source_connector_factory_defaults_to_warehouse(monkeypatch) -> None:
    monkeypatch.delenv("SOURCE_CONNECTOR_MODE", raising=False)
    get_settings.cache_clear()

    assert build_source_connector() is None


def test_source_connector_factory_can_select_local_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "local_file")
    monkeypatch.setenv("LOCAL_FILE_CONNECTOR_ROOT", str(tmp_path))
    get_settings.cache_clear()

    connector = build_source_connector()

    assert isinstance(connector, LocalFileConnector)
    assert connector.health()["base_dir"] == str(tmp_path.resolve())


def test_source_connector_factory_can_select_github_repository(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "github_repository")
    monkeypatch.setenv("GITHUB_CONNECTOR_ACCESS_TOKEN", "token")
    get_settings.cache_clear()

    connector = build_source_connector()

    assert isinstance(connector, GitHubRepositoryConnector)
    assert connector.health()["authenticated"] is True
    assert isinstance(build_source_connector_for_type("github_repository"), GitHubRepositoryConnector)


def test_source_connector_factory_rejects_unknown_mode(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_CONNECTOR_MODE", "unknown")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="unsupported"):
        build_source_connector()
