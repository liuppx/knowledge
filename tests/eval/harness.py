"""Retrieval eval harness: seeds the Q01–Q12 corpus, runs three retrieval tiers
and writes a JSON + Markdown report.

Tiers toggle the product flags only; the ranking code under test is the real
``ServiceSearchService`` evidence path with the permission/availability filter
in its default allow-all posture (quality, not authorization, is measured here).

  lexical        retrieval_hybrid_enabled=False, retrieval_rerank_enabled=False
  hybrid         retrieval_hybrid_enabled=True,  retrieval_rerank_enabled=False
  hybrid_rerank  retrieval_hybrid_enabled=True,  retrieval_rerank_enabled=True
"""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from knowledge.core.settings import get_settings
from knowledge.db.session import SessionLocal
from knowledge.models import EvidenceUnit, KnowledgeBase, Source, SourceAsset, WalletUser
from knowledge.services.service_search import ServiceSearchService
from knowledge.services.unit_retrieval import UnitEmbeddingIndexer

from tests.eval.dataset import DOCS, QUESTIONS
from tests.eval.providers import resolve_providers

TIERS: tuple[str, ...] = ("lexical", "hybrid", "hybrid_rerank")
TOP_K = 6
DEFAULT_REPORT_DIR = Path(".eval")


def seed_corpus(db) -> tuple[int, str, dict[int, str]]:
    """Create a fresh KB holding every corpus passage as an EvidenceUnit.

    Returns (kb_id, owner_wallet, {evidence_id: doc_key}). One SourceAsset per
    document so hits carry a realistic per-document source path.
    """
    wallet = f"0x{uuid.uuid4().hex[:20]}"
    db.add(WalletUser(wallet_address=wallet))
    db.flush()
    kb = KnowledgeBase(owner_wallet_address=wallet, name="Knowledge Product Handbook (eval)")
    db.add(kb)
    db.flush()
    source = Source(kb_id=kb.id, source_path=f"/eval/{uuid.uuid4().hex}", scope_type="directory")
    db.add(source)
    db.flush()
    evidence_docs: dict[int, str] = {}
    for doc_key, doc in DOCS.items():
        asset = SourceAsset(
            kb_id=kb.id,
            source_id=source.id,
            asset_path=f"{source.source_path}/{doc['file']}",
            asset_name=doc["file"],
            availability_status="available",
        )
        db.add(asset)
        db.flush()
        for passage in doc["passages"]:
            unit = EvidenceUnit(kb_id=kb.id, asset_id=asset.id, text=passage)
            db.add(unit)
            db.flush()
            evidence_docs[unit.id] = doc_key
    db.commit()
    return kb.id, wallet, evidence_docs


@contextmanager
def _tier_flags(settings, tier: str):
    saved = (settings.retrieval_hybrid_enabled, settings.retrieval_rerank_enabled)
    settings.retrieval_hybrid_enabled = tier in ("hybrid", "hybrid_rerank")
    settings.retrieval_rerank_enabled = tier == "hybrid_rerank"
    try:
        yield
    finally:
        settings.retrieval_hybrid_enabled, settings.retrieval_rerank_enabled = saved


def _run_question(service: ServiceSearchService, db, kb_id: int, evidence_docs: dict[int, str], question: dict) -> dict:
    trace: dict = {}
    hits = service._search_evidence(
        db,
        kb_id=kb_id,
        query=question["query"],
        result_view="compact",
        availability_mode="allow_all",
        top_k=TOP_K,
        exclude_evidence_ids=set(),
        trace=trace,
    )
    ranked_docs: list[str] = []
    for hit in hits:
        doc_key = evidence_docs.get(hit.evidence_id, "?")
        if doc_key not in ranked_docs:
            ranked_docs.append(doc_key)
    expected = set(question["expected"])
    first_rank = next((index + 1 for index, doc in enumerate(ranked_docs) if doc in expected), None)
    found = expected & set(ranked_docs)
    return {
        "id": question["id"],
        "kind": question["kind"],
        "query": question["query"],
        "expected": sorted(expected),
        "retrieved_docs": ranked_docs,
        "hit_count": len(hits),
        "top_score": hits[0].score if hits else None,
        "hit": bool(found),
        "recall": (len(found) / len(expected)) if expected else None,
        "first_rank": first_rank,
        "reciprocal_rank": (1.0 / first_rank) if first_rank else 0.0,
        "trace": {key: trace.get(key) for key in ("vector_signal", "vector_widened", "rerank_signal", "rerank_count")},
    }


def _aggregate(results: list[dict]) -> dict:
    scored = [result for result in results if result["expected"]]
    count = len(scored) or 1
    return {
        "scored_questions": len(scored),
        "hits": sum(1 for result in scored if result["hit"]),
        "hit_rate": round(sum(1 for result in scored if result["hit"]) / count, 4),
        "recall_at_k": round(sum(result["recall"] for result in scored) / count, 4),
        "mrr": round(sum(result["reciprocal_rank"] for result in scored) / count, 4),
    }


def run_eval(report_dir: Path | None = None) -> dict:
    settings = get_settings()
    embedding, rerank, provider_label = resolve_providers()
    started = time.time()
    with SessionLocal() as db:
        kb_id, wallet, evidence_docs = seed_corpus(db)
        backfill = UnitEmbeddingIndexer(embedding_provider=embedding).backfill_kb(
            db, kb_id=kb_id, owner_wallet_address=wallet
        )
        service = ServiceSearchService(embedding_provider=embedding, rerank_provider=rerank)
        tiers: dict[str, dict] = {}
        for tier in TIERS:
            with _tier_flags(settings, tier):
                results = [_run_question(service, db, kb_id, evidence_docs, question) for question in QUESTIONS]
            tiers[tier] = {"summary": _aggregate(results), "questions": results}

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_seconds": round(time.time() - started, 3),
        "provider": provider_label,
        "vector_store_mode": settings.vector_store_mode,
        "top_k": TOP_K,
        "corpus": {"documents": len(DOCS), "passages": sum(len(doc["passages"]) for doc in DOCS.values()), "backfill": backfill},
        "tiers": {tier: data["summary"] for tier, data in tiers.items()},
        "questions": {
            question["id"]: {
                "kind": question["kind"],
                "query": question["query"],
                "expected": question["expected"],
                "note": question.get("note", ""),
                "by_tier": {tier: _strip(tiers[tier]["questions"][index]) for tier in TIERS},
            }
            for index, question in enumerate(QUESTIONS)
        },
    }
    _write_report(report, report_dir or Path(os.environ.get("KNOWLEDGE_EVAL_REPORT_DIR", DEFAULT_REPORT_DIR)))
    return report


def _strip(result: dict) -> dict:
    return {key: value for key, value in result.items() if key not in ("id", "kind", "query", "expected")}


def _write_report(report: dict, report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "retrieval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "retrieval_report.md").write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict) -> str:
    lines = [
        "## Retrieval eval (Q01–Q12)",
        "",
        f"- provider: `{report['provider']}`",
        f"- vector_store_mode: `{report['vector_store_mode']}`  top_k: {report['top_k']}  "
        f"corpus: {report['corpus']['documents']} docs / {report['corpus']['passages']} passages",
        "",
        "| tier | hit@k | recall@k | MRR |",
        "| --- | --- | --- | --- |",
    ]
    for tier in TIERS:
        summary = report["tiers"][tier]
        lines.append(
            f"| {tier} | {summary['hits']}/{summary['scored_questions']} ({summary['hit_rate']:.2f}) "
            f"| {summary['recall_at_k']:.2f} | {summary['mrr']:.3f} |"
        )
    lines += ["", "| ID | kind | " + " | ".join(f"{tier} rank" for tier in TIERS) + " | note |", "| --- | --- | " + " | ".join("---" for _ in TIERS) + " | --- |"]
    for question_id, question in report["questions"].items():
        cells = []
        for tier in TIERS:
            result = question["by_tier"][tier]
            if not question["expected"]:
                cells.append(f"info: {', '.join(result['retrieved_docs'][:3]) or '∅'}")
            else:
                cells.append(str(result["first_rank"]) if result["first_rank"] else "miss")
        lines.append(f"| {question_id} | {question['kind']} | " + " | ".join(cells) + f" | {question.get('note', '')} |")
    lines.append("")
    return "\n".join(lines)
