from __future__ import annotations

import os

import pytest

from knowledge.core.settings import get_settings
from knowledge.services.unit_retrieval import WeaviateUnitVectorIndex


pytestmark = pytest.mark.skipif(
    os.environ.get("VECTOR_STORE_MODE") != "weaviate",
    reason="requires a live Weaviate (VECTOR_STORE_MODE=weaviate)",
)


@pytest.fixture()
def unit_index():
    # A per-test class keeps this round-trip isolated from any production data.
    settings = get_settings()
    settings.weaviate_unit_index_name = "KnowledgeUnitTest"
    index = WeaviateUnitVectorIndex()
    client = index._connect()
    if client.collections.exists("KnowledgeUnitTest"):
        client.collections.delete("KnowledgeUnitTest")
    index._client = None  # force schema recreation on next connect
    try:
        yield index
    finally:
        client = index._connect()
        if client.collections.exists("KnowledgeUnitTest"):
            client.collections.delete("KnowledgeUnitTest")
        index.close()


def test_upsert_and_near_vector_round_trip(unit_index):
    model = "roundtrip-model"
    # Three orthogonal unit vectors; the query aligns with unit 30.
    records = [
        {"kb_id": 1, "unit_kind": "evidence", "unit_id": 10, "embedding_model": model, "vector": [1.0, 0.0, 0.0]},
        {"kb_id": 1, "unit_kind": "evidence", "unit_id": 20, "embedding_model": model, "vector": [0.0, 1.0, 0.0]},
        {"kb_id": 1, "unit_kind": "evidence", "unit_id": 30, "embedding_model": model, "vector": [0.0, 0.0, 1.0]},
        # Different KB: must be excluded by the filter.
        {"kb_id": 2, "unit_kind": "evidence", "unit_id": 99, "embedding_model": model, "vector": [0.0, 0.0, 1.0]},
    ]
    result = unit_index.upsert(records)
    assert result["indexed"] == 4

    scores = unit_index.score_map(
        None, kb_id=1, kind="evidence", query_vector=[0.0, 0.0, 1.0], embedding_model=model, limit=10
    )
    assert 99 not in scores  # kb_id filter holds
    assert set(scores) <= {10, 20, 30}
    assert scores[30] == pytest.approx(1.0, abs=1e-3)  # exact match -> cosine ~1
    assert scores[30] > scores.get(10, -1.0)
    assert scores[30] > scores.get(20, -1.0)


def test_upsert_is_idempotent(unit_index):
    model = "roundtrip-model"
    record = {"kb_id": 5, "unit_kind": "evidence", "unit_id": 7, "embedding_model": model, "vector": [1.0, 0.0]}
    unit_index.upsert([record])
    # Re-upserting the same unit must overwrite, not duplicate.
    unit_index.upsert([{**record, "vector": [0.0, 1.0]}])

    scores = unit_index.score_map(
        None, kb_id=5, kind="evidence", query_vector=[0.0, 1.0], embedding_model=model, limit=10
    )
    assert list(scores) == [7]
    assert scores[7] == pytest.approx(1.0, abs=1e-3)
