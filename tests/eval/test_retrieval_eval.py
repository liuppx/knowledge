"""Q01–Q12 retrieval quality gate. Runs via ``scripts/test.sh --suite eval``.

Excluded from the default pytest run (marker ``eval``). The CI job publishing
this report is non-blocking until the live-provider baseline stabilises; the
assertions below encode the floor we do enforce even offline.
"""

from __future__ import annotations

import os

import pytest

from tests.eval.harness import TIERS, run_eval

pytestmark = pytest.mark.eval

# Mirrors docs/产品验证知识库.md §6: Q01–Q11 must hit on at least 9 questions.
MIN_HITS = int(os.environ.get("KNOWLEDGE_EVAL_MIN_HITS", "9"))


@pytest.fixture(scope="module")
def report() -> dict:
    return run_eval()


def test_report_covers_all_tiers_and_questions(report):
    assert set(report["tiers"]) == set(TIERS)
    assert len(report["questions"]) == 12
    assert report["corpus"]["backfill"]["indexed"] == report["corpus"]["passages"]
    for question in report["questions"].values():
        assert set(question["by_tier"]) == set(TIERS)


def test_hybrid_tiers_actually_engaged(report):
    # Guards against a silently-skipped tier (e.g. mock provider) inflating the comparison.
    q01 = report["questions"]["Q01"]["by_tier"]
    assert q01["lexical"]["trace"]["vector_signal"] == "disabled"
    assert q01["hybrid"]["trace"]["vector_signal"] == "active"
    assert q01["hybrid_rerank"]["trace"]["vector_signal"] == "active"
    assert q01["hybrid_rerank"]["trace"]["rerank_signal"] == "active"


def test_hybrid_rerank_not_worse_than_lexical(report):
    lexical = report["tiers"]["lexical"]
    best = report["tiers"]["hybrid_rerank"]
    assert best["hit_rate"] >= lexical["hit_rate"], (lexical, best)
    assert best["mrr"] >= lexical["mrr"] - 1e-9, (lexical, best)


def test_hybrid_rerank_meets_hit_floor(report):
    best = report["tiers"]["hybrid_rerank"]
    assert best["hits"] >= MIN_HITS, best


def test_no_answer_question_is_informational(report):
    # Q12 has no gold document: retrieval cannot "abstain", the answer layer must.
    # We only record what surfaced so reviewers can judge fabrication risk.
    q12 = report["questions"]["Q12"]
    assert q12["expected"] == []
    for tier in TIERS:
        assert q12["by_tier"][tier]["recall"] is None
