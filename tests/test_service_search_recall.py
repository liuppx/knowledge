from __future__ import annotations

import uuid

import pytest

from knowledge.db.session import SessionLocal
from knowledge.models import (
    EvidenceUnit,
    KnowledgeBase,
    Source,
    SourceAsset,
    WalletUser,
)
from knowledge.services.embedding import EmbeddingProvider, MockEmbeddingProvider
from knowledge.services.service_search import ServiceSearchService
from knowledge.services import service_search as service_search_module
from knowledge.services.unit_retrieval import (
    DBUnitVectorIndex,
    UnitEmbeddingIndexer,
    WeaviateUnitVectorIndex,
    build_unit_vector_index,
    close_unit_vector_index,
)


class _FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic non-mock provider: maps exact texts to fixed vectors."""

    provider_name = "fake"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[text] for text in texts]


# Query "alpha" lexically matches only E1; E3 ("gamma gamma") is the semantic twin of
# the query, so only vector recall can surface it. E2 is orthogonal noise.
_QUERY = "alpha"
_E1_TEXT = "alpha alpha"
_E2_TEXT = "beta beta"
_E3_TEXT = "gamma gamma"
_VECTORS = {
    _QUERY: [1.0, 0.0, 0.0],
    _E1_TEXT: [0.0, 1.0, 0.0],  # lexical hit, semantically distant
    _E2_TEXT: [0.0, 0.0, 1.0],  # orthogonal to the query
    _E3_TEXT: [1.0, 0.0, 0.0],  # cosine 1.0 with the query, zero lexical overlap
}


def _seed_kb(db) -> int:
    wallet = f"0x{uuid.uuid4().hex[:20]}"
    db.add(WalletUser(wallet_address=wallet))
    db.flush()
    kb = KnowledgeBase(owner_wallet_address=wallet, name="recall-kb")
    db.add(kb)
    db.flush()
    source = Source(kb_id=kb.id, source_path=f"/recall/{uuid.uuid4().hex}", scope_type="directory")
    db.add(source)
    db.flush()
    asset = SourceAsset(
        kb_id=kb.id,
        source_id=source.id,
        asset_path="/recall/doc.txt",
        asset_name="doc.txt",
        availability_status="available",
    )
    db.add(asset)
    db.flush()
    for text in (_E1_TEXT, _E2_TEXT, _E3_TEXT):
        db.add(EvidenceUnit(kb_id=kb.id, asset_id=asset.id, text=text))
    db.commit()
    return kb.id, wallet


def _search_evidence(service: ServiceSearchService, db, kb_id: int, trace: dict):
    return service._search_evidence(
        db,
        kb_id=kb_id,
        query=_QUERY,
        result_view="compact",
        availability_mode="allow_all",
        top_k=6,
        exclude_evidence_ids=set(),
        trace=trace,
    )


def test_vector_recall_widens_beyond_lexical():
    provider = _FakeEmbeddingProvider(_VECTORS)
    with SessionLocal() as db:
        kb_id, wallet = _seed_kb(db)
        UnitEmbeddingIndexer(embedding_provider=provider).backfill_kb(
            db, kb_id=kb_id, owner_wallet_address=wallet
        )
        trace: dict = {}
        hits = _search_evidence(ServiceSearchService(embedding_provider=provider), db, kb_id, trace)

    texts = [hit.text for hit in hits]
    # Lexical recall alone returns only E1; vector recall pulls in the semantic twin E3.
    assert _E1_TEXT in texts
    assert _E3_TEXT in texts
    assert trace["vector_signal"] == "active"
    assert trace["vector_widened"] >= 1


def test_mock_provider_stays_lexical_only():
    provider = MockEmbeddingProvider(dimensions=8)
    with SessionLocal() as db:
        kb_id, wallet = _seed_kb(db)
        # Even if something backfilled, the mock provider must not activate hybrid recall.
        trace: dict = {}
        hits = _search_evidence(ServiceSearchService(embedding_provider=provider), db, kb_id, trace)

    texts = [hit.text for hit in hits]
    assert texts == [_E1_TEXT]
    assert trace["vector_signal"] == "mock_skipped"


def test_active_without_backfill_degrades_to_lexical():
    provider = _FakeEmbeddingProvider(_VECTORS)
    with SessionLocal() as db:
        kb_id, _wallet = _seed_kb(db)  # no backfill: unit_embeddings is empty for this KB
        trace: dict = {}
        hits = _search_evidence(ServiceSearchService(embedding_provider=provider), db, kb_id, trace)

    texts = [hit.text for hit in hits]
    assert texts == [_E1_TEXT]
    assert trace["vector_signal"] == "active_no_index"


def test_backfill_is_idempotent():
    provider = _FakeEmbeddingProvider(_VECTORS)
    indexer = UnitEmbeddingIndexer(embedding_provider=provider)
    with SessionLocal() as db:
        kb_id, wallet = _seed_kb(db)
        first = indexer.backfill_kb(db, kb_id=kb_id, owner_wallet_address=wallet)
        second = indexer.backfill_kb(db, kb_id=kb_id, owner_wallet_address=wallet)

    assert first["indexed"] == 3
    assert first["skipped"] == 0
    # Unchanged texts on the second pass embed nothing.
    assert second["indexed"] == 0
    assert second["skipped"] == 3


def test_build_unit_vector_index_routes_on_vector_store_mode(monkeypatch):
    from knowledge.core.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "vector_store_mode", "db", raising=False)
    assert isinstance(build_unit_vector_index(), DBUnitVectorIndex)

    monkeypatch.setattr(settings, "vector_store_mode", "weaviate", raising=False)
    try:
        index = build_unit_vector_index()
        assert isinstance(index, WeaviateUnitVectorIndex)
        # Cached: repeated builds reuse the same connection-holding instance.
        assert build_unit_vector_index() is index
    finally:
        close_unit_vector_index()


class _ExplodingUnitIndex:
    backend_name = "weaviate"

    def score_map(self, *args, **kwargs):
        raise RuntimeError("weaviate unreachable")


def test_vector_backend_outage_degrades_to_lexical(monkeypatch):
    provider = _FakeEmbeddingProvider(_VECTORS)
    monkeypatch.setattr(service_search_module, "build_unit_vector_index", lambda: _ExplodingUnitIndex())
    with SessionLocal() as db:
        kb_id, wallet = _seed_kb(db)
        UnitEmbeddingIndexer(embedding_provider=provider).backfill_kb(
            db, kb_id=kb_id, owner_wallet_address=wallet
        )
        trace: dict = {}
        hits = _search_evidence(ServiceSearchService(embedding_provider=provider), db, kb_id, trace)

    # Search still returns the lexical hit rather than 500-ing on the backend outage.
    assert [hit.text for hit in hits] == [_E1_TEXT]
    assert trace["vector_signal"].startswith("degraded:")
