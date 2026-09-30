from __future__ import annotations

import httpx
import pytest

from knowledge.core.settings import get_settings
from knowledge.services import rerank as rerank_module
from knowledge.services.embedding import OpenAICompatibleEmbeddingProvider, build_embedding_provider
from knowledge.services.rerank import OpenAICompatibleRerankProvider, build_rerank_provider


def _gateway(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "model_provider_mode", "openai_compatible", raising=False)
    monkeypatch.setattr(settings, "model_gateway_base_url", "http://router.test/v1", raising=False)
    monkeypatch.setattr(settings, "embedding_timeout_seconds", 7, raising=False)
    monkeypatch.setattr(settings, "embedding_max_retries", 3, raising=False)
    monkeypatch.setattr(settings, "rerank_timeout_seconds", 4, raising=False)
    monkeypatch.setattr(settings, "rerank_max_retries", 1, raising=False)


def test_embedding_factory_applies_timeout_and_retry_policy(monkeypatch):
    _gateway(monkeypatch)
    provider = build_embedding_provider()
    assert isinstance(provider, OpenAICompatibleEmbeddingProvider)
    assert provider.client.request_timeout == 7
    assert provider.client.max_retries == 3
    assert provider.diagnostics()["max_retries"] == 3


def test_rerank_factory_applies_timeout_and_retry_policy(monkeypatch):
    _gateway(monkeypatch)
    provider = build_rerank_provider()
    assert isinstance(provider, OpenAICompatibleRerankProvider)
    assert provider.timeout_seconds == 4
    assert provider.max_retries == 1


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=httpx.Request("POST", "http://router.test/v1/rerank"), response=httpx.Response(self.status_code))

    def json(self) -> dict:
        return self._payload


def _provider() -> OpenAICompatibleRerankProvider:
    return OpenAICompatibleRerankProvider(base_url="http://router.test/v1", api_key="", model="m", timeout_seconds=1, max_retries=1)


def test_rerank_retries_transport_error_then_succeeds(monkeypatch):
    calls: list[int] = []

    def post(url, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("refused")
        return _Response(200, {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}]})

    monkeypatch.setattr(rerank_module.httpx, "post", post)
    assert _provider().rerank("q", ["a", "b"]) == [0.1, 0.9]
    assert len(calls) == 2


def test_rerank_retries_5xx_but_not_4xx(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(rerank_module.httpx, "post", lambda url, **kwargs: (calls.append(1), _Response(503))[1])
    with pytest.raises(httpx.HTTPStatusError):
        _provider().rerank("q", ["a"])
    assert len(calls) == 2  # initial + 1 retry, then gives up

    calls.clear()
    monkeypatch.setattr(rerank_module.httpx, "post", lambda url, **kwargs: (calls.append(1), _Response(401))[1])
    with pytest.raises(httpx.HTTPStatusError):
        _provider().rerank("q", ["a"])
    assert len(calls) == 1  # 4xx is not retried
