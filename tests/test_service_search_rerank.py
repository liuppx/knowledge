from __future__ import annotations

from knowledge.core.settings import get_settings
from knowledge.schemas.service_search import ServiceSearchHit
from knowledge.services.embedding import EmbeddingProvider
from knowledge.services.rerank import MockRerankProvider, RerankProvider
from knowledge.services.service_search import ServiceSearchService


class _MockEmbedding(EmbeddingProvider):
    """Mock embedding so hybrid stays skipped; the test isolates the rerank stage."""

    provider_name = "mock"

    def embed_texts(self, texts):
        return [[0.0] for _ in texts]


class _FakeReranker(RerankProvider):
    """Deterministic non-mock reranker: score by exact text lookup."""

    provider_name = "fake"

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [self._scores[doc] for doc in documents]


class _ExplodingReranker(RerankProvider):
    provider_name = "fake"

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        raise RuntimeError("rerank gateway timeout")


def _hit(text: str, score: float) -> ServiceSearchHit:
    return ServiceSearchHit(
        result_kind="evidence",
        score=score,
        text=text,
        content_health_status="active",
        source_health_summary="available",
    )


def _entries() -> list[dict]:
    # Fused order (as produced upstream): A, B, C.
    return [
        {"keyword_score": 0.9, "text": "A", "hit": _hit("A", 0.9)},
        {"keyword_score": 0.5, "text": "B", "hit": _hit("B", 0.5)},
        {"keyword_score": 0.1, "text": "C", "hit": _hit("C", 0.1)},
    ]


def _service(reranker: RerankProvider) -> ServiceSearchService:
    return ServiceSearchService(embedding_provider=_MockEmbedding(), rerank_provider=reranker)


def test_rerank_reorders_fused_candidates():
    # Reranker judges C most relevant, then A, then B -> order becomes C, A, B.
    service = _service(_FakeReranker({"A": 0.2, "B": 0.1, "C": 0.9}))
    trace: dict = {}
    ordered = service._emit("Q", _entries(), trace)

    assert [hit.text for hit in ordered] == ["C", "A", "B"]
    # Scores now reflect rerank relevance and stay non-increasing along the order.
    assert ordered[0].score >= ordered[1].score >= ordered[2].score
    assert trace["rerank_enabled"] is True
    assert trace["rerank_signal"] == "active"
    assert trace["rerank_count"] == 3


def test_mock_reranker_keeps_fused_order():
    service = _service(MockRerankProvider())
    trace: dict = {}
    ordered = service._emit("Q", _entries(), trace)

    assert [hit.text for hit in ordered] == ["A", "B", "C"]
    assert trace["rerank_signal"] == "mock_skipped"


def test_rerank_degrades_to_fused_order_on_error():
    service = _service(_ExplodingReranker())
    trace: dict = {}
    ordered = service._emit("Q", _entries(), trace)

    assert [hit.text for hit in ordered] == ["A", "B", "C"]
    assert trace["rerank_signal"].startswith("degraded:")


def test_rerank_disabled_flag_keeps_fused_order(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "retrieval_rerank_enabled", False, raising=False)
    service = _service(_FakeReranker({}))
    trace: dict = {}
    ordered = service._emit("Q", _entries(), trace)

    assert [hit.text for hit in ordered] == ["A", "B", "C"]
    assert trace["rerank_signal"] == "disabled"


def test_rerank_only_touches_top_m(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rerank_top_m", 2, raising=False)
    # Only A,B are eligible; C stays pinned to the tail even if it would score highest.
    service = _service(_FakeReranker({"A": 0.1, "B": 0.9, "C": 5.0}))
    trace: dict = {}
    ordered = service._emit("Q", _entries(), trace)

    assert [hit.text for hit in ordered] == ["B", "A", "C"]
    assert trace["rerank_count"] == 2
