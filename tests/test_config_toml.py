from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_settings import SettingsError

from knowledge.core import settings as settings_module
from knowledge.core.settings import ProductionConfigError, Settings, TomlSettingsSource, get_settings


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated config directory; the repo's config/ files are not read."""
    monkeypatch.setenv("KNOWLEDGE_CONFIG_DIR", str(tmp_path))
    # Settings fields these tests assert on must not come from the shell.
    for name in ("APP_NAME", "DEBUG", "APP_ENV", "JWT_SECRET", "TOKEN_ENCRYPTION_SECRET", "WAREHOUSE_APP_ID", "CHUNK_SIZE"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _write(config_dir: Path, name: str, body: str) -> Path:
    path = config_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def test_defaults_toml_is_loaded(config_dir: Path) -> None:
    _write(config_dir, "defaults.toml", '[application]\napp_name = "from-defaults"\ndebug = false\n')
    settings = Settings()
    assert settings.app_name == "from-defaults"
    assert settings.debug is False


def test_local_overrides_defaults_only_for_keys_it_declares(config_dir: Path) -> None:
    _write(config_dir, "defaults.toml", '[application]\napp_name = "from-defaults"\ndebug = false\n')
    _write(config_dir, "local.toml", '[application]\napp_name = "from-local"\n')
    settings = Settings()
    assert settings.app_name == "from-local"
    assert settings.debug is False  # untouched by local.toml


def test_env_overrides_both_files(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(config_dir, "defaults.toml", '[application]\napp_name = "from-defaults"\n')
    _write(config_dir, "local.toml", '[application]\napp_name = "from-local"\n')
    monkeypatch.setenv("APP_NAME", "from-env")
    assert Settings().app_name == "from-env"


def test_dotenv_overrides_files_but_not_process_env(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(config_dir, "local.toml", '[application]\napp_name = "from-local"\n')
    env_file = _write(config_dir, "test.env", "APP_NAME=from-dotenv\n")
    monkeypatch.setenv("KNOWLEDGE_ENV_FILE", str(env_file))
    # env_file is read from model_config at class creation; pass it explicitly here.
    assert Settings(_env_file=env_file).app_name == "from-dotenv"
    monkeypatch.setenv("APP_NAME", "from-env")
    assert Settings(_env_file=env_file).app_name == "from-env"


def test_tables_are_flattened_and_other_fields_keep_defaults(config_dir: Path) -> None:
    _write(config_dir, "defaults.toml", '[application]\napp_name = "x"\n[warehouse]\nwarehouse_app_id = "y"\n[retrieval]\nchunk_size = 123\n')
    settings = Settings()
    assert settings.app_name == "x"
    assert settings.warehouse_app_id == "y"
    assert settings.chunk_size == 123
    assert settings.app_env == "development"
    assert settings.worker_run_lease_ttl_seconds == 120


def test_missing_files_fall_back_to_field_defaults(config_dir: Path) -> None:
    settings = Settings()
    assert settings.app_name == "knowledge"
    assert settings.vector_store_mode == "db"


def test_malformed_toml_names_the_file(config_dir: Path) -> None:
    _write(config_dir, "defaults.toml", "[application\nnot valid")
    with pytest.raises(SettingsError, match="defaults.toml"):
        Settings()


def test_unknown_key_fails_fast(config_dir: Path) -> None:
    _write(config_dir, "local.toml", '[application]\napp_nmae = "typo"\n')
    with pytest.raises(SettingsError, match="app_nmae"):
        Settings()


def test_source_order_puts_env_before_config_files() -> None:
    sources = Settings.settings_customise_sources(Settings, init_settings=None, env_settings="env", dotenv_settings="dotenv", file_secret_settings="secrets")  # type: ignore[arg-type]
    toml_positions = [index for index, source in enumerate(sources) if isinstance(source, TomlSettingsSource)]
    assert sources[1] == "env" and sources[2] == "dotenv"
    assert toml_positions == [4, 5]
    assert sources[4].file_path.name == "local.toml" and sources[5].file_path.name == "defaults.toml"


def test_config_dir_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_CONFIG_DIR", "/custom/path")
    assert settings_module.config_dir() == Path("/custom/path")
    monkeypatch.delenv("KNOWLEDGE_CONFIG_DIR")
    assert settings_module.config_dir() == settings_module._PROJECT_ROOT / "config"


def test_shipped_config_files_load_and_match_code_defaults() -> None:
    """config/defaults.toml must mirror the field defaults; local.toml ships commented out."""
    get_settings.cache_clear()
    shipped = TomlSettingsSource(Settings, settings_module._PROJECT_ROOT / "config" / "defaults.toml")()
    assert shipped, "defaults.toml should declare settings"
    for key, value in shipped.items():
        assert value == Settings.model_fields[key].default, key
    local = TomlSettingsSource(Settings, settings_module._PROJECT_ROOT / "config" / "local.toml")()
    assert local == {}, "local.toml must not set values in the repo (placeholders are comments)"


def test_production_guard_sees_config_file_values(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MODEL_PROVIDER_MODE", "openai_compatible")
    monkeypatch.setenv("MODEL_GATEWAY_BASE_URL", "http://router.test/v1")
    monkeypatch.setenv("WAREHOUSE_GATEWAY_MODE", "")
    _write(config_dir, "local.toml", '[application]\ndebug = false\njwt_secret = "change-me-in-production"\ntoken_encryption_secret = "real-secret"\n')
    with pytest.raises(ProductionConfigError, match="JWT_SECRET"):
        get_settings()

    get_settings.cache_clear()
    _write(config_dir, "local.toml", '[application]\ndebug = false\njwt_secret = "a-real-long-random-secret"\ntoken_encryption_secret = "real-secret"\n')
    settings = get_settings()
    assert settings.app_env == "production"
    assert settings.debug is False
    assert settings.model_provider_mode == "openai_compatible"
