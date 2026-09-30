from __future__ import annotations

import hashlib

import httpx

from knowledge.core.settings import get_settings


class RerankProvider:
    """Cross-encoder rerank over (query, documents). Returns one relevance score per
    document, aligned to the input order. Higher is more relevant."""

    provider_name = "unknown"

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        raise NotImplementedError

    def diagnostics(self) -> dict:
        return {"provider_name": self.provider_name}


class MockRerankProvider(RerankProvider):
    """Deterministic, offline reranker. Gated off in the retrieval path (like the mock
    embedding provider) so it never perturbs the default/test ordering; exists so the
    factory always returns a provider and diagnostics stay uniform."""

    provider_name = "mock"

    def __init__(self, configured_mode: str = "mock", fallback_reason: str = "") -> None:
        self.configured_mode = configured_mode
        self.fallback_reason = fallback_reason

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        scores: list[float] = []
        for document in documents:
            digest = hashlib.sha256(f"{query}\x00{document}".encode("utf-8")).digest()
            scores.append(int.from_bytes(digest[:4], "big") / 0xFFFFFFFF)
        return scores

    def diagnostics(self) -> dict:
        return {
            "provider_name": self.provider_name,
            "configured_mode": self.configured_mode,
            "fallback_reason": self.fallback_reason,
        }


class OpenAICompatibleRerankProvider(RerankProvider):
    """Cohere/Jina-style ``POST {base_url}/rerank`` reranker (the shape Router exposes).

    Request:  {"model", "query", "documents": [...], "top_n"}
    Response: {"results": [{"index", "relevance_score"}, ...]}  (order not guaranteed)
    """

    provider_name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            f"{self.base_url}/rerank",
            headers=headers,
            json={
                "model": self.model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        # Map results back to input order; unranked documents default to 0.0.
        scores = [0.0] * len(documents)
        for item in payload.get("results", []):
            index = int(item.get("index", -1))
            if 0 <= index < len(scores):
                scores[index] = float(item.get("relevance_score", 0.0))
        return scores

    def diagnostics(self) -> dict:
        return {
            "provider_name": self.provider_name,
            "configured_mode": self.provider_name,
            "base_url": self.base_url,
            "model": self.model,
            "fallback_reason": "",
        }


def build_rerank_provider() -> RerankProvider:
    settings = get_settings()
    if settings.model_provider_mode == "openai_compatible" and settings.model_gateway_base_url:
        return OpenAICompatibleRerankProvider(
            base_url=settings.model_gateway_base_url,
            api_key=settings.model_gateway_api_key,
            model=settings.rerank_model,
            timeout_seconds=settings.rerank_timeout_seconds,
        )
    fallback_reason = ""
    if settings.model_provider_mode == "openai_compatible" and not settings.model_gateway_base_url:
        fallback_reason = "model_gateway_base_url missing; using mock rerank provider"
    return MockRerankProvider(configured_mode=settings.model_provider_mode, fallback_reason=fallback_reason)
