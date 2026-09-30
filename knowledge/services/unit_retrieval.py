from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.core.settings import get_settings
from knowledge.models import EvidenceUnit, KnowledgeBase, UnitEmbeddingRecord
from knowledge.services.embedding import EmbeddingProvider, build_embedding_provider


def _text_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5 or 1.0
    right_norm = sum(b * b for b in right) ** 0.5 or 1.0
    return numerator / (left_norm * right_norm)


class UnitEmbeddingIndexer:
    """Embeds governed units and upserts unit-level vectors for retrieval recall.

    v1.0 indexes evidence units (the large pool where lexical recall most often
    misses semantically-relevant matches). Formal knowledge units remain on the
    lexical-recall rerank path; the ``unit_kind`` column reserves room to index
    them later without a schema change.
    """

    def __init__(self, embedding_provider: EmbeddingProvider | None = None) -> None:
        self._embedding_provider = embedding_provider

    def _embedding(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = build_embedding_provider()
        return self._embedding_provider

    def reindex_kb(self, db: Session, *, wallet_address: str, kb_id: int) -> dict:
        """Owner-scoped entry point for the reindex-units endpoint. Raises LookupError on 404."""
        kb = db.get(KnowledgeBase, kb_id)
        if kb is None or kb.owner_wallet_address != wallet_address:
            raise LookupError("knowledge base not found")
        return self.backfill_kb(db, kb_id=kb_id, owner_wallet_address=kb.owner_wallet_address)

    def backfill_kb(self, db: Session, *, kb_id: int, owner_wallet_address: str) -> dict:
        """(Re)embed all evidence units of a KB and upsert their vectors. Idempotent."""
        embedding_model = get_settings().embedding_model
        rows = db.execute(
            select(EvidenceUnit.id, EvidenceUnit.text)
            .where(EvidenceUnit.kb_id == kb_id)
            .order_by(EvidenceUnit.id.asc())
        ).all()
        if not rows:
            return {"kind": "evidence", "kb_id": kb_id, "indexed": 0, "skipped": 0}

        existing = {
            record.unit_id: record
            for record in db.scalars(
                select(UnitEmbeddingRecord)
                .where(UnitEmbeddingRecord.kb_id == kb_id)
                .where(UnitEmbeddingRecord.unit_kind == "evidence")
                .where(UnitEmbeddingRecord.embedding_model == embedding_model)
            ).all()
        }

        # Only embed units whose text changed since the last backfill.
        to_embed: list[tuple[int, str, str]] = []
        skipped = 0
        for unit_id, text in rows:
            digest = _text_hash(text)
            record = existing.get(unit_id)
            if record is not None and record.text_hash == digest and record.index_status == "indexed":
                skipped += 1
                continue
            to_embed.append((unit_id, text or "", digest))

        if not to_embed:
            return {"kind": "evidence", "kb_id": kb_id, "indexed": 0, "skipped": skipped}

        vectors = self._embedding().embed_texts([text for _, text, _ in to_embed])
        for (unit_id, _text, digest), vector in zip(to_embed, vectors):
            record = existing.get(unit_id)
            if record is None:
                db.add(
                    UnitEmbeddingRecord(
                        kb_id=kb_id,
                        owner_wallet_address=owner_wallet_address,
                        unit_kind="evidence",
                        unit_id=unit_id,
                        text_hash=digest,
                        embedding_model=embedding_model,
                        index_status="indexed",
                        vector_json=vector,
                    )
                )
            else:
                record.text_hash = digest
                record.vector_json = vector
                record.index_status = "indexed"
                record.owner_wallet_address = owner_wallet_address
        db.commit()
        result = {"kind": "evidence", "kb_id": kb_id, "indexed": len(to_embed), "skipped": skipped}

        # Postgres is the source of truth; when a Weaviate accelerator is configured,
        # mirror the freshly-embedded vectors into it. Best-effort: a mirror failure is
        # reported but never rolls back the durable write (the DB backend still serves).
        index = build_unit_vector_index()
        if getattr(index, "backend_name", "db") == "weaviate":
            payloads = [
                {
                    "kb_id": kb_id,
                    "unit_kind": "evidence",
                    "unit_id": unit_id,
                    "embedding_model": embedding_model,
                    "vector": vector,
                }
                for (unit_id, _text, _digest), vector in zip(to_embed, vectors)
            ]
            try:
                result["weaviate"] = index.upsert(payloads)
            except Exception as exc:  # noqa: BLE001 - mirror is best-effort
                result["weaviate"] = {"status": f"error: {exc}", "indexed": 0}
        return result


class DBUnitVectorIndex:
    """Postgres-backed unit vector index: O(n) cosine per KB. Always available; the
    fallback whenever Weaviate is not configured or is unreachable."""

    backend_name = "db"

    def score_map(
        self,
        db: Session,
        *,
        kb_id: int,
        kind: str,
        query_vector: list[float],
        embedding_model: str,
        limit: int | None = None,
    ) -> dict[int, float]:
        """Return ``unit_id -> cosine(query, unit)`` for every indexed unit of the KB/kind/model."""
        _ = limit  # the caller slices the widening set; DB scan returns all candidates
        rows = db.execute(
            select(UnitEmbeddingRecord.unit_id, UnitEmbeddingRecord.vector_json)
            .where(UnitEmbeddingRecord.kb_id == kb_id)
            .where(UnitEmbeddingRecord.unit_kind == kind)
            .where(UnitEmbeddingRecord.embedding_model == embedding_model)
            .where(UnitEmbeddingRecord.index_status == "indexed")
        ).all()
        return {unit_id: _cosine_similarity(query_vector, vector) for unit_id, vector in rows}


class WeaviateUnitVectorIndex:
    """Weaviate-backed ANN index for unit vectors, rebuilt from the Postgres source of
    truth. Its own class (``weaviate_unit_index_name``) keeps unit vectors separate from
    chunk vectors. weaviate imports are lazy so the DB default never loads the client."""

    backend_name = "weaviate"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None

    def _connect(self):
        if self._client is not None:
            return self._client
        import weaviate
        from weaviate.auth import AuthApiKey

        auth = AuthApiKey(self.settings.weaviate_api_key) if self.settings.weaviate_api_key else None
        client = weaviate.connect_to_custom(
            http_host=self.settings.weaviate_host,
            http_port=self.settings.weaviate_port,
            http_secure=self.settings.weaviate_scheme == "https",
            grpc_host=self.settings.weaviate_host,
            grpc_port=self.settings.weaviate_grpc_port,
            grpc_secure=self.settings.weaviate_scheme == "https",
            auth_credentials=auth,
            skip_init_checks=False,
        )
        self._ensure_schema(client)
        self._client = client
        return client

    def _ensure_schema(self, client) -> None:
        import weaviate.classes.config as wc

        name = self.settings.weaviate_unit_index_name
        if client.collections.exists(name):
            return
        client.collections.create(
            name=name,
            properties=[
                wc.Property(name="kb_id", data_type=wc.DataType.INT, skip_vectorization=True),
                wc.Property(name="unit_kind", data_type=wc.DataType.TEXT, skip_vectorization=True),
                wc.Property(name="unit_id", data_type=wc.DataType.INT, skip_vectorization=True),
                wc.Property(name="embedding_model", data_type=wc.DataType.TEXT, skip_vectorization=True),
            ],
            vectorizer_config=wc.Configure.Vectorizer.none(),
        )

    @staticmethod
    def _object_uuid(kb_id: int, unit_kind: str, unit_id: int, embedding_model: str):
        import uuid

        return uuid.uuid5(uuid.NAMESPACE_URL, f"unit:{kb_id}:{unit_kind}:{unit_id}:{embedding_model}")

    def upsert(self, records: list[dict]) -> dict:
        """Idempotently write unit vectors keyed by a deterministic UUID (kb/kind/id/model)."""
        client = self._connect()
        collection = client.collections.get(self.settings.weaviate_unit_index_name)
        count = 0
        for record in records:
            object_id = self._object_uuid(
                record["kb_id"], record["unit_kind"], record["unit_id"], record["embedding_model"]
            )
            properties = {
                "kb_id": record["kb_id"],
                "unit_kind": record["unit_kind"],
                "unit_id": record["unit_id"],
                "embedding_model": record["embedding_model"],
            }
            if collection.data.exists(object_id):
                collection.data.delete_by_id(object_id)
            collection.data.insert(properties=properties, uuid=object_id, vector=record["vector"])
            count += 1
        return {"status": "ok", "indexed": count, "index_name": self.settings.weaviate_unit_index_name}

    def score_map(
        self,
        db: Session,
        *,
        kb_id: int,
        kind: str,
        query_vector: list[float],
        embedding_model: str,
        limit: int | None = None,
    ) -> dict[int, float]:
        _ = db
        from weaviate.classes.query import Filter, MetadataQuery

        client = self._connect()
        collection = client.collections.get(self.settings.weaviate_unit_index_name)
        where = (
            Filter.by_property("kb_id").equal(kb_id)
            & Filter.by_property("unit_kind").equal(kind)
            & Filter.by_property("embedding_model").equal(embedding_model)
        )
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=limit or get_settings().retrieval_vector_top_k,
            filters=where,
            return_metadata=MetadataQuery(distance=True),
            return_properties=["unit_id"],
        )
        scores: dict[int, float] = {}
        for obj in response.objects:
            unit_id = int(obj.properties.get("unit_id") or 0)
            distance = obj.metadata.distance if obj.metadata and obj.metadata.distance is not None else 1.0
            scores[unit_id] = 1.0 - float(distance)  # Weaviate returns cosine distance
        return scores

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None


_UNIT_INDEX_SINGLETON: dict[str, WeaviateUnitVectorIndex] = {}


def build_unit_vector_index():
    """Return the configured unit vector backend. Weaviate reuses a cached connection;
    the DB backend is a cheap per-call object and the universal fallback."""
    if get_settings().vector_store_mode == "weaviate":
        index = _UNIT_INDEX_SINGLETON.get("weaviate")
        if index is None:
            index = WeaviateUnitVectorIndex()
            _UNIT_INDEX_SINGLETON["weaviate"] = index
        return index
    return DBUnitVectorIndex()


def close_unit_vector_index() -> None:
    index = _UNIT_INDEX_SINGLETON.pop("weaviate", None)
    if index is not None:
        index.close()
