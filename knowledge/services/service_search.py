from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from knowledge.core.settings import get_settings
from knowledge.models import (
    EvidenceUnit,
    KBRelease,
    KBReleaseItem,
    KnowledgeBase,
    KnowledgeItem,
    KnowledgeItemEvidenceLink,
    KnowledgeItemRevision,
    RetrievalLog,
    SourceAsset,
)
from knowledge.schemas.future_domain import KBReleaseRead, ServiceGrantRead
from knowledge.schemas.grants import ServiceGrantResolvedRead
from knowledge.schemas.service_search import (
    RESULT_VIEWS,
    ServiceSearchEvidenceSummary,
    ServiceSearchHit,
    ServiceSearchResponse,
    ServiceSearchSourceHealthDetail,
)
from knowledge.services.embedding import EmbeddingProvider, build_embedding_provider
from knowledge.services.rerank import RerankProvider, build_rerank_provider
from knowledge.services.release_management import ReleaseManagementService
from knowledge.services.unit_retrieval import build_unit_vector_index
from knowledge.services.service_grants import ServiceGrantService
from knowledge.services.service_principals import ServicePrincipalService


ALLOWED_MODES = {"formal_first", "formal_only", "evidence_only"}
ALLOWED_RESULT_VIEWS = set(RESULT_VIEWS)
ALLOWED_AVAILABILITY_MODES = {"allow_all", "healthy_only", "exclude_source_missing"}


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)


@dataclass
class FormalCandidate:
    release_item: KBReleaseItem
    item: KnowledgeItem
    revision: KnowledgeItemRevision
    evidence_links: list[KnowledgeItemEvidenceLink]
    evidence_units: list[EvidenceUnit]
    source_assets: list[SourceAsset]


@dataclass
class EvidenceCandidate:
    evidence: EvidenceUnit
    asset: SourceAsset


class ServiceSearchService:
    def __init__(
        self,
        principal_service: ServicePrincipalService | None = None,
        grant_service: ServiceGrantService | None = None,
        release_management_service: ReleaseManagementService | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        rerank_provider: RerankProvider | None = None,
    ) -> None:
        self.principal_service = principal_service or ServicePrincipalService()
        self.release_management_service = release_management_service or ReleaseManagementService()
        self.grant_service = grant_service or ServiceGrantService(
            principal_service=self.principal_service,
            release_management_service=self.release_management_service,
        )
        self._embedding_provider = embedding_provider
        self._rerank_provider = rerank_provider

    def search(
        self,
        db: Session,
        *,
        service_api_key: str,
        kb_id: int,
        query: str,
        mode: str,
        result_view: str | None,
        availability_mode: str,
        top_k: int,
    ) -> ServiceSearchResponse:
        normalized_mode = self._normalize_choice(mode, ALLOWED_MODES, "mode")
        normalized_availability = self._normalize_choice(availability_mode, ALLOWED_AVAILABILITY_MODES, "availability_mode")
        principal = self.principal_service.verify_api_key(db, service_api_key)
        grant = self._resolve_grant_for_kb(db, principal.id, kb_id)
        release = self._resolve_release_for_search(db, grant, normalized_mode)
        normalized_view = self._resolve_result_view(result_view, grant.default_result_mode)

        formal_hits: list[ServiceSearchHit] = []
        evidence_hits: list[ServiceSearchHit] = []
        used_evidence_ids: set[int] = set()
        retrieval_trace: dict = {}
        if normalized_mode in {"formal_first", "formal_only"} and release is not None:
            formal_hits = self._search_formal(
                db,
                release,
                query,
                normalized_view,
                normalized_availability,
                top_k,
                used_evidence_ids=used_evidence_ids,
                trace=retrieval_trace,
            )
        if normalized_mode == "evidence_only":
            evidence_hits = self._search_evidence(
                db,
                kb_id=kb_id,
                query=query,
                result_view=normalized_view,
                availability_mode=normalized_availability,
                top_k=top_k,
                exclude_evidence_ids=set(),
                trace=retrieval_trace,
            )
        elif normalized_mode == "formal_first":
            remaining = max(0, top_k - len(formal_hits))
            if remaining > 0:
                evidence_hits = self._search_evidence(
                    db,
                    kb_id=kb_id,
                    query=query,
                    result_view=normalized_view,
                    availability_mode=normalized_availability,
                    top_k=remaining,
                    exclude_evidence_ids=used_evidence_ids,
                    trace=retrieval_trace,
                )
        hits = formal_hits if normalized_mode == "formal_only" else evidence_hits if normalized_mode == "evidence_only" else [*formal_hits, *evidence_hits]
        if normalized_mode == "formal_only" and release is None:
            hits = []

        resolved_grant = self._resolved_grant_read(db, grant, release)
        self.grant_service.mark_grant_used(db, grant)
        response = ServiceSearchResponse(
            kb_id=kb_id,
            mode=normalized_mode,
            result_view=normalized_view,
            availability_mode=normalized_availability,
            release=release,
            grant=resolved_grant,
            hits=hits[:top_k],
        )
        self.record_retrieval_log(
            db,
            owner_wallet_address=grant.owner_wallet_address,
            kb_id=kb_id,
            service_grant_id=grant.id,
            service_principal_id=principal.id,
            query=query,
            query_mode=normalized_mode,
            release_id=release.id if release is not None else None,
            response=response,
            retrieval_trace=retrieval_trace,
        )
        return response

    def _search_formal(
        self,
        db: Session,
        release: KBRelease,
        query: str,
        result_view: str,
        availability_mode: str,
        top_k: int,
        include_zero_scores: bool = False,
        used_evidence_ids: set[int] | None = None,
        trace: dict | None = None,
    ) -> list[ServiceSearchHit]:
        rows = db.execute(
            select(KBReleaseItem, KnowledgeItem, KnowledgeItemRevision)
            .join(KnowledgeItem, KnowledgeItem.id == KBReleaseItem.knowledge_item_id)
            .join(KnowledgeItemRevision, KnowledgeItemRevision.id == KBReleaseItem.knowledge_item_revision_id)
            .where(KBReleaseItem.release_id == release.id)
            .order_by(KBReleaseItem.knowledge_item_id.asc(), KBReleaseItem.id.asc())
        ).all()
        entries: list[dict] = []
        for release_item, item, revision in rows:
            evidence_links = list(
                db.scalars(
                    select(KnowledgeItemEvidenceLink)
                    .options(selectinload(KnowledgeItemEvidenceLink.evidence_unit))
                    .where(KnowledgeItemEvidenceLink.knowledge_item_revision_id == revision.id)
                    .order_by(KnowledgeItemEvidenceLink.rank.asc(), KnowledgeItemEvidenceLink.id.asc())
                ).all()
            )
            evidence_units = [link.evidence_unit for link in evidence_links if link.evidence_unit is not None]
            asset_ids = [evidence.asset_id for evidence in evidence_units]
            source_assets = list(
                db.scalars(select(SourceAsset).where(SourceAsset.id.in_(asset_ids)))  # type: ignore[arg-type]
            ) if asset_ids else []
            health = self._content_health_for_assets(source_assets)
            if not self._availability_allowed(health, availability_mode):
                continue
            score = self._formal_score(query, revision.title, revision.statement, item.is_hotfix, health)
            if score <= 0 and not include_zero_scores:
                continue
            if used_evidence_ids is not None:
                used_evidence_ids.update(evidence.id for evidence in evidence_units)
            entries.append(
                {
                    "keyword_score": max(score, 0.0),
                    "text": f"{revision.title} {revision.statement}",
                    "hit": self._formal_hit(
                        score=max(score, 0.0),
                        release_item=release_item,
                        item=item,
                        revision=revision,
                        evidence_units=evidence_units,
                        source_assets=source_assets,
                        result_view=result_view,
                        health=health,
                    ),
                }
            )
        return self._rank_entries(query, entries, trace)[:top_k]

    def _search_evidence(
        self,
        db: Session,
        *,
        kb_id: int,
        query: str,
        result_view: str,
        availability_mode: str,
        top_k: int,
        exclude_evidence_ids: set[int],
        include_zero_scores: bool = False,
        trace: dict | None = None,
    ) -> list[ServiceSearchHit]:
        rows = db.execute(
            select(EvidenceUnit, SourceAsset)
            .join(SourceAsset, SourceAsset.id == EvidenceUnit.asset_id)
            .where(EvidenceUnit.kb_id == kb_id)
            .order_by(EvidenceUnit.asset_id.asc(), EvidenceUnit.id.asc())
        ).all()
        # Availability-passing, non-excluded rows form the pool: lexical hits plus the
        # units that vector recall may pull in (widening beyond token overlap).
        pool: dict[int, tuple[EvidenceUnit, SourceAsset, str]] = {}
        entries: list[dict] = []
        present_ids: set[int] = set()
        for evidence, asset in rows:
            if evidence.id in exclude_evidence_ids:
                continue
            health = self._content_health_for_assets([asset])
            if not self._availability_allowed(health, availability_mode):
                continue
            pool[evidence.id] = (evidence, asset, health)
            score = self._evidence_score(query, evidence.text)
            if score <= 0 and not include_zero_scores:
                continue
            entries.append(self._evidence_entry(evidence.id, evidence, asset, result_view, health, score))
            present_ids.add(evidence.id)

        settings = get_settings()
        active, note = self._hybrid_status(settings)
        if trace is not None:
            trace["hybrid_enabled"] = settings.retrieval_hybrid_enabled
            if trace.get("vector_signal") in (None, "active"):
                trace["vector_signal"] = note
        if not active:
            entries.sort(key=lambda entry: entry["keyword_score"], reverse=True)
            return self._emit(query, entries, trace)[:top_k]

        try:
            query_vector = self._embedding().embed_query(query)
        except Exception as exc:  # noqa: BLE001 - retrieval must not fail on model errors
            if trace is not None:
                trace["vector_signal"] = f"degraded:{type(exc).__name__}"
            entries.sort(key=lambda entry: entry["keyword_score"], reverse=True)
            return self._emit(query, entries, trace)[:top_k]

        try:
            score_map = build_unit_vector_index().score_map(
                db, kb_id=kb_id, kind="evidence", query_vector=query_vector, embedding_model=settings.embedding_model
            )
        except Exception as exc:  # noqa: BLE001 - a vector-backend outage must not fail search
            if trace is not None:
                trace["vector_signal"] = f"degraded:{type(exc).__name__}"
            entries.sort(key=lambda entry: entry["keyword_score"], reverse=True)
            return self._emit(query, entries, trace)[:top_k]
        if not score_map:
            # Nothing backfilled yet: degrade to lexical rather than fuse a meaningless signal.
            if trace is not None:
                trace["vector_signal"] = "active_no_index"
            entries.sort(key=lambda entry: entry["keyword_score"], reverse=True)
            return self._emit(query, entries, trace)[:top_k]

        widened = 0
        for unit_id, _score in sorted(score_map.items(), key=lambda kv: kv[1], reverse=True)[: settings.retrieval_vector_top_k]:
            if unit_id in present_ids:
                continue
            row = pool.get(unit_id)
            if row is None:  # excluded or availability-filtered
                continue
            evidence, asset, health = row
            entries.append(self._evidence_entry(unit_id, evidence, asset, result_view, health, 0.0))
            present_ids.add(unit_id)
            widened += 1
        if trace is not None:
            trace["vector_signal"] = "active"
            trace["vector_widened"] = widened
        vector_scores = [score_map.get(entry["evidence_id"], -1.0) for entry in entries]
        return self._emit(query, self._fuse(entries, vector_scores), trace)[:top_k]

    def _evidence_entry(
        self,
        evidence_id: int,
        evidence: EvidenceUnit,
        asset: SourceAsset,
        result_view: str,
        health: str,
        keyword_score: float,
    ) -> dict:
        return {
            "evidence_id": evidence_id,
            "keyword_score": max(keyword_score, 0.0),
            "text": evidence.text,
            "hit": self._evidence_hit(
                score=max(keyword_score, 0.0),
                evidence=evidence,
                asset=asset,
                result_view=result_view,
                health=health,
            ),
        }

    def _rank_entries(self, query: str, entries: list[dict], trace: dict | None) -> list[ServiceSearchHit]:
        """Order candidate hits, fusing lexical and semantic signals when hybrid is active.

        Hybrid retrieval re-ranks the lexical recall set with Reciprocal Rank Fusion
        (RRF): each candidate gets a lexical rank (token-overlap score) and a semantic
        rank (query/candidate embedding cosine), and the fused score is
        ``sum(1 / (k + rank))``. RRF depends only on ranks, so the incomparable scales
        of the two signals never need normalizing. Only active with a real embedding
        provider; the mock provider is skipped so lexical ordering stays deterministic.
        Any embedding failure degrades gracefully to lexical-only.
        """
        if not entries:
            return []
        settings = get_settings()
        active, note = self._hybrid_status(settings)
        if trace is not None:
            trace["hybrid_enabled"] = settings.retrieval_hybrid_enabled
            # Surface a skip/degrade note over a plain "active" when both branches run.
            if trace.get("vector_signal") in (None, "active"):
                trace["vector_signal"] = note

        if not active:
            entries.sort(key=lambda entry: entry["keyword_score"], reverse=True)
            return self._emit(query, entries, trace)

        try:
            vectors = self._embedding().embed_texts([query, *[entry["text"] for entry in entries]])
        except Exception as exc:  # noqa: BLE001 - retrieval must not fail on model errors
            if trace is not None:
                trace["vector_signal"] = f"degraded:{type(exc).__name__}"
            entries.sort(key=lambda entry: entry["keyword_score"], reverse=True)
            return self._emit(query, entries, trace)

        query_vector = vectors[0]
        candidate_vectors = vectors[1:]
        vector_scores = [_cosine_similarity(query_vector, vector) for vector in candidate_vectors]
        if trace is not None:
            trace["vector_signal"] = "active"
        return self._emit(query, self._fuse(entries, vector_scores), trace)

    def _fuse(self, entries: list[dict], vector_scores: list[float]) -> list[dict]:
        """Reciprocal Rank Fusion of lexical and semantic ranks; sets each hit's fused
        score and returns the entries in fused order (rerank may reorder them next)."""
        keyword_ranks = self._rank_positions([entry["keyword_score"] for entry in entries])
        vector_ranks = self._rank_positions(vector_scores)
        k = get_settings().retrieval_rrf_k
        for index, entry in enumerate(entries):
            fused = 1.0 / (k + keyword_ranks[index]) + 1.0 / (k + vector_ranks[index])
            entry["fused"] = fused
            entry["hit"].score = round(fused, 6)
        order = sorted(range(len(entries)), key=lambda index: (-entries[index]["fused"], index))
        return [entries[index] for index in order]

    def _emit(self, query: str, entries: list[dict], trace: dict | None) -> list[ServiceSearchHit]:
        """Final stage over ranked entries: optional rerank, then materialize hits."""
        return [entry["hit"] for entry in self._rerank_entries(query, entries, trace)]

    def _rerank_entries(self, query: str, entries: list[dict], trace: dict | None) -> list[dict]:
        """Re-score the top ``rerank_top_m`` fused candidates with a cross-encoder and
        reorder them; the tail keeps its fused order. Active only with a real rerank
        provider (mock is skipped for determinism). Any failure degrades to fused order.
        """
        if len(entries) < 2:
            return entries
        settings = get_settings()
        active, note = self._rerank_status(settings)
        if trace is not None:
            trace["rerank_enabled"] = settings.retrieval_rerank_enabled
            trace["rerank_signal"] = note
        if not active:
            return entries

        top_m = max(1, settings.rerank_top_m)
        head = entries[:top_m]
        tail = entries[top_m:]
        try:
            scores = self._rerank().rerank(query, [entry["text"] for entry in head])
        except Exception as exc:  # noqa: BLE001 - rerank must not fail the search
            if trace is not None:
                trace["rerank_signal"] = f"degraded:{type(exc).__name__}"
            return entries
        if len(scores) != len(head):
            if trace is not None:
                trace["rerank_signal"] = "degraded:bad_response"
            return entries

        for entry, score in zip(head, scores):
            entry["hit"].score = round(float(score), 6)
        order = sorted(range(len(head)), key=lambda index: (-scores[index], index))
        if trace is not None:
            trace["rerank_signal"] = "active"
            trace["rerank_count"] = len(head)
        return [head[index] for index in order] + tail

    def _hybrid_status(self, settings) -> tuple[bool, str]:
        if not settings.retrieval_hybrid_enabled:
            return False, "disabled"
        provider = self._embedding()
        if getattr(provider, "provider_name", "mock") == "mock":
            return False, "mock_skipped"
        return True, "active"

    def _rerank_status(self, settings) -> tuple[bool, str]:
        if not settings.retrieval_rerank_enabled:
            return False, "disabled"
        provider = self._rerank()
        if getattr(provider, "provider_name", "mock") == "mock":
            return False, "mock_skipped"
        return True, "active"

    def _rerank(self) -> RerankProvider:
        if self._rerank_provider is None:
            self._rerank_provider = build_rerank_provider()
        return self._rerank_provider

    def _embedding(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = build_embedding_provider()
        return self._embedding_provider

    @staticmethod
    def _rank_positions(scores: list[float]) -> list[int]:
        """Return 1-based rank per index by descending score, ties broken by index."""
        order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
        ranks = [0] * len(scores)
        for position, index in enumerate(order, start=1):
            ranks[index] = position
        return ranks

    def _formal_hit(
        self,
        *,
        score: float,
        release_item: KBReleaseItem,
        item: KnowledgeItem,
        revision: KnowledgeItemRevision,
        evidence_units: list[EvidenceUnit],
        source_assets: list[SourceAsset],
        result_view: str,
        health: str,
    ) -> ServiceSearchHit:
        source_refs = list(dict.fromkeys(asset.asset_path for asset in source_assets))
        asset_by_id = {asset.id: asset for asset in source_assets}
        hit = ServiceSearchHit(
            result_kind="formal",
            score=round(score, 6),
            content_health_status=release_item.content_health_status if release_item.content_health_status != "healthy" else health,
            source_health_summary=health,
            source_refs=source_refs if result_view in {"referenced", "audit"} else [],
            knowledge_item_id=item.id,
            knowledge_item_revision_id=revision.id,
            title=revision.title,
            statement=revision.statement,
            item_type=item.item_type,
            updated_at=revision.updated_at.isoformat(),
        )
        if result_view == "audit":
            hit.evidence_summaries = [
                ServiceSearchEvidenceSummary(
                    evidence_id=evidence.id,
                    evidence_type=evidence.evidence_type,
                    text_excerpt=evidence.text[:200],
                    content_health_status=self._content_health_for_assets([asset_by_id[evidence.asset_id]])
                    if asset_by_id.get(evidence.asset_id) is not None
                    else health,
                    source_ref=asset_by_id[evidence.asset_id].asset_path if asset_by_id.get(evidence.asset_id) is not None else "",
                )
                for evidence in evidence_units
            ]
            hit.source_health_details = [
                ServiceSearchSourceHealthDetail(
                    source_id=asset.source_id,
                    asset_id=asset.id,
                    asset_path=asset.asset_path,
                    availability_status=asset.availability_status,
                )
                for asset in source_assets
            ]
            hit.audit_info = {
                "ranking_factors": {
                    "mode": "formal",
                    "is_hotfix": item.is_hotfix,
                    "health_penalty": 0.1 if health == "source_missing" else 0.03 if health == "stale" else 0.0,
                },
                "release_item": {
                    "release_id": release_item.release_id,
                    "item_version_hash": release_item.item_version_hash,
                },
            }
        return hit

    def _evidence_hit(
        self,
        *,
        score: float,
        evidence: EvidenceUnit,
        asset: SourceAsset,
        result_view: str,
        health: str,
    ) -> ServiceSearchHit:
        hit = ServiceSearchHit(
            result_kind="evidence",
            score=round(score, 6),
            content_health_status=health,
            source_health_summary=health,
            source_refs=[asset.asset_path] if result_view in {"referenced", "audit"} else [],
            evidence_id=evidence.id,
            evidence_type=evidence.evidence_type,
            text=evidence.text,
        )
        if result_view == "audit":
            hit.source_health_details = [
                ServiceSearchSourceHealthDetail(
                    source_id=asset.source_id,
                    asset_id=asset.id,
                    asset_path=asset.asset_path,
                    availability_status=asset.availability_status,
                )
            ]
            hit.audit_info = {
                "ranking_factors": {
                    "mode": "evidence",
                    "health_penalty": 0.1 if health == "source_missing" else 0.03 if health == "stale" else 0.0,
                },
                "source_locator": evidence.source_locator,
            }
        return hit

    def _resolve_grant_for_kb(self, db: Session, principal_id: int, kb_id: int):
        grants = self.grant_service.list_grants_for_principal(db, principal_id)
        grant = next((item for item in grants if item.kb_id == kb_id), None)
        if grant is None:
            raise LookupError("service grant not found for knowledge base")
        return grant

    def _resolve_release_for_search(self, db: Session, grant, mode: str) -> KBRelease | None:
        try:
            return self.grant_service.resolve_release_for_grant(db, grant)
        except LookupError:
            if mode in {"evidence_only", "formal_first"}:
                return None
            raise

    def _resolved_grant_read(self, db: Session, grant, release: KBRelease | None) -> ServiceGrantResolvedRead:
        kb_row = db.get(KnowledgeBase, grant.kb_id)
        return ServiceGrantResolvedRead(
            **ServiceGrantRead.model_validate(grant).model_dump(),
            kb_name=kb_row.name if kb_row is not None else None,
            resolved_release=KBReleaseRead.model_validate(release) if release is not None else None,
        )

    @staticmethod
    def _content_health_for_assets(source_assets: list[SourceAsset]) -> str:
        if not source_assets:
            return "healthy"
        statuses = {asset.availability_status for asset in source_assets}
        if "missing" in statuses:
            return "source_missing"
        if "missing_unconfirmed" in statuses or "changed" in statuses:
            return "stale"
        return "healthy"

    @staticmethod
    def _availability_allowed(health: str, availability_mode: str) -> bool:
        if availability_mode == "healthy_only":
            return health == "healthy"
        if availability_mode == "exclude_source_missing":
            return health != "source_missing"
        return True

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.findall(r"[A-Za-z0-9_]+", str(text or "").lower()) if token}

    def _formal_score(self, query: str, title: str, statement: str, is_hotfix: bool, health: str) -> float:
        base = self._text_score(query, f"{title} {statement}")
        if base <= 0:
            return 0.0
        boost = 0.05 if is_hotfix else 0.0
        penalty = 0.1 if health == "source_missing" else 0.03 if health == "stale" else 0.0
        return max(0.0, base + boost - penalty)

    def _evidence_score(self, query: str, text: str) -> float:
        return self._text_score(query, text)

    def _text_score(self, query: str, text: str) -> float:
        query_tokens = self._tokenize(query)
        text_tokens = self._tokenize(text)
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = len(query_tokens & text_tokens) / len(query_tokens)
        query_lower = str(query or "").strip().lower()
        text_lower = str(text or "").strip().lower()
        phrase_bonus = 0.2 if query_lower and query_lower in text_lower else 0.0
        return overlap + phrase_bonus

    @staticmethod
    def _normalize_choice(value: str, allowed: set[str], field_name: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in allowed:
            raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed))}")
        return normalized

    def _resolve_result_view(self, requested_result_view: str | None, default_result_mode: str | None) -> str:
        if requested_result_view is not None:
            return self._normalize_choice(requested_result_view, ALLOWED_RESULT_VIEWS, "result_view")
        return self._normalize_choice(default_result_mode or RESULT_VIEWS[0], ALLOWED_RESULT_VIEWS, "default_result_mode")

    def record_retrieval_log(
        self,
        db: Session,
        *,
        owner_wallet_address: str,
        kb_id: int,
        service_grant_id: int | None,
        service_principal_id: int | None,
        query: str,
        query_mode: str,
        release_id: int | None,
        response: ServiceSearchResponse,
        retrieval_trace: dict | None = None,
    ) -> RetrievalLog:
        health_counts: dict[str, int] = {}
        for hit in response.hits:
            health_counts[hit.content_health_status] = health_counts.get(hit.content_health_status, 0) + 1
        top_hit = response.hits[0] if response.hits else None
        log = RetrievalLog(
            owner_wallet_address=owner_wallet_address,
            kb_id=kb_id,
            service_grant_id=service_grant_id,
            service_principal_id=service_principal_id,
            query=query,
            query_mode=query_mode,
            release_id=release_id,
            result_summary_json={
                "hit_count": len(response.hits),
                "result_kinds": [hit.result_kind for hit in response.hits],
                "health_counts": health_counts,
                "top_hit": {
                    "result_kind": top_hit.result_kind,
                    "knowledge_item_id": top_hit.knowledge_item_id,
                    "knowledge_item_revision_id": top_hit.knowledge_item_revision_id,
                    "evidence_id": top_hit.evidence_id,
                    "content_health_status": top_hit.content_health_status,
                }
                if top_hit is not None
                else None,
            },
            trace_json={
                "mode": response.mode,
                "result_view": response.result_view,
                "availability_mode": response.availability_mode,
                "release_selection_mode": response.grant.release_selection_mode if response.grant is not None else None,
                "hybrid": retrieval_trace or {},
                "hits": [
                    {
                        "result_kind": hit.result_kind,
                        "knowledge_item_id": hit.knowledge_item_id,
                        "knowledge_item_revision_id": hit.knowledge_item_revision_id,
                        "evidence_id": hit.evidence_id,
                        "content_health_status": hit.content_health_status,
                        "score": hit.score,
                    }
                    for hit in response.hits
                ],
            },
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log
