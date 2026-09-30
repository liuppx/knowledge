from __future__ import annotations

import pytest

from knowledge.core.settings import get_settings
from knowledge.schemas.service_search import ServiceSearchHit
from knowledge.services.embedding import EmbeddingProvider, MockEmbeddingProvider
from knowledge.services.service_search import ServiceSearchService


class _FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic non-mock provider: maps exact texts to fixed vectors."""

    provider_name = "fake"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[text] for text in texts]


class _ExplodingEmbeddingProvider(EmbeddingProvider):
    provider_name = "fake"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("gateway timeout")


def _hit(text: str, score: float) -> ServiceSearchHit:
    return ServiceSearchHit(
        result_kind="evidence",
        score=score,
        content_health_status="healthy",
        source_health_summary="healthy",
        text=text,
    )


def _entries() -> list[dict]:
    # Lexical order by keyword_score: A > B > C
    return [
        {"keyword_score": 0.9, "text": "A", "hit": _hit("A", 0.9)},
        {"keyword_score": 0.5, "text": "B", "hit": _hit("B", 0.5)},
        {"keyword_score": 0.1, "text": "C", "hit": _hit("C", 0.1)},
    ]


def test_hybrid_rrf_reorders_with_real_provider():
    query = "Q"
    # Vector similarity to query: C (1.0) > A (0.6) > B (0.0)
    provider = _FakeEmbeddingProvider(
        {
            "Q": [1.0, 0.0, 0.0],
            "A": [0.6, 0.8, 0.0],
            "B": [0.0, 1.0, 0.0],
            "C": [1.0, 0.0, 0.0],
        }
    )
    service = ServiceSearchService(embedding_provider=provider)
    entries = _entries()
    trace: dict = {}

    ordered = service._rank_entries(query, entries, trace)

    # Keyword ranks: A=1,B=2,C=3 ; vector ranks: C=1,A=2,B=3.
    # RRF(k=60): A=1/61+1/62 > C=1/63+1/61 > B=1/62+1/63.
    # So the lexical-worst C is fused above B: order becomes A, C, B.
    assert [hit.text for hit in ordered] == ["A", "C", "B"]
    # Scores now reflect fused values and are non-increasing along the order.
    assert ordered[0].score >= ordered[1].score >= ordered[2].score
    assert trace["hybrid_enabled"] is True
    assert trace["vector_signal"] == "active"


def test_mock_provider_skips_hybrid_and_keeps_lexical_order():
    service = ServiceSearchService(
        embedding_provider=MockEmbeddingProvider(dimensions=8)
    )
    entries = _entries()
    trace: dict = {}

    ordered = service._rank_entries("Q", entries, trace)

    assert [hit.text for hit in ordered] == ["A", "B", "C"]
    assert trace["vector_signal"] == "mock_skipped"


def test_hybrid_degrades_to_lexical_on_embedding_error():
    service = ServiceSearchService(embedding_provider=_ExplodingEmbeddingProvider())
    entries = _entries()
    trace: dict = {}

    ordered = service._rank_entries("Q", entries, trace)

    assert [hit.text for hit in ordered] == ["A", "B", "C"]
    assert trace["vector_signal"].startswith("degraded:")


def test_hybrid_disabled_flag_keeps_lexical_order(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "retrieval_hybrid_enabled", False, raising=False)
    # A real provider is present, but the flag is off -> lexical only, provider unused.
    provider = _FakeEmbeddingProvider({})
    service = ServiceSearchService(embedding_provider=provider)
    entries = _entries()
    trace: dict = {}

    ordered = service._rank_entries("Q", entries, trace)

    assert [hit.text for hit in ordered] == ["A", "B", "C"]
    assert trace["vector_signal"] == "disabled"


def test_empty_entries_return_empty():
    service = ServiceSearchService(embedding_provider=_FakeEmbeddingProvider({}))
    assert service._rank_entries("Q", [], {}) == []
