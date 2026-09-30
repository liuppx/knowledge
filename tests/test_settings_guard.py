from __future__ import annotations

import pytest

from knowledge.core.settings import (
    DEFAULT_JWT_SECRET,
    ProductionConfigError,
    Settings,
    validate_runtime_settings,
)


SECURE_SECRET = "s" * 48


def _settings(**overrides) -> Settings:
    base = dict(
        app_env="production",
        debug=False,
        jwt_secret=SECURE_SECRET,
        model_provider_mode="gateway",
        warehouse_gateway_mode="",
        token_encryption_secret=SECURE_SECRET,
    )
    base.update(overrides)
    return Settings(**base)


def test_development_is_exempt() -> None:
    settings = _settings(
        app_env="development",
        debug=True,
        jwt_secret=DEFAULT_JWT_SECRET,
        model_provider_mode="mock",
    )
    validate_runtime_settings(settings, token_secret_explicit=False)


def test_secure_production_passes() -> None:
    validate_runtime_settings(_settings(), token_secret_explicit=True)


def test_default_jwt_secret_rejected() -> None:
    with pytest.raises(ProductionConfigError, match="JWT_SECRET"):
        validate_runtime_settings(_settings(jwt_secret=DEFAULT_JWT_SECRET), token_secret_explicit=True)


def test_placeholder_jwt_secret_rejected() -> None:
    with pytest.raises(ProductionConfigError, match="JWT_SECRET"):
        validate_runtime_settings(
            _settings(jwt_secret="replace-with-a-random-secret"), token_secret_explicit=True
        )


def test_debug_rejected() -> None:
    with pytest.raises(ProductionConfigError, match="DEBUG"):
        validate_runtime_settings(_settings(debug=True), token_secret_explicit=True)


def test_mock_model_rejected() -> None:
    with pytest.raises(ProductionConfigError, match="MODEL_PROVIDER_MODE"):
        validate_runtime_settings(_settings(model_provider_mode="mock"), token_secret_explicit=True)


def test_mock_warehouse_rejected() -> None:
    with pytest.raises(ProductionConfigError, match="WAREHOUSE_GATEWAY_MODE"):
        validate_runtime_settings(_settings(warehouse_gateway_mode="mock"), token_secret_explicit=True)


def test_derived_token_secret_rejected() -> None:
    with pytest.raises(ProductionConfigError, match="TOKEN_ENCRYPTION_SECRET"):
        validate_runtime_settings(_settings(), token_secret_explicit=False)


def test_all_problems_reported_together() -> None:
    settings = _settings(
        debug=True,
        jwt_secret=DEFAULT_JWT_SECRET,
        model_provider_mode="mock",
        warehouse_gateway_mode="mock",
    )
    with pytest.raises(ProductionConfigError) as excinfo:
        validate_runtime_settings(settings, token_secret_explicit=False)
    message = str(excinfo.value)
    for token in ("JWT_SECRET", "DEBUG", "MODEL_PROVIDER_MODE", "WAREHOUSE_GATEWAY_MODE", "TOKEN_ENCRYPTION_SECRET"):
        assert token in message
