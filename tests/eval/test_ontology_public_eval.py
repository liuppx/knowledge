"""Networked ontology V1 public-data proxy pilot.

Run explicitly with ``scripts/test.sh --suite ontology-eval``.  It is excluded
from the default suite because it reads fixed records from three public APIs.
"""

from __future__ import annotations

import pytest

from tests.eval.ontology_public_dataset import EXPECTED_NORMALIZED_SOURCE_SHA256
from tests.eval.ontology_public_harness import run_public_ontology_eval


pytestmark = pytest.mark.ontology_eval


@pytest.fixture(scope="module")
def report() -> dict:
    return run_public_ontology_eval()


def test_dataset_shape_and_source_integrity(report):
    dataset = report["dataset"]
    assert dataset["usa_award_families"] == 10
    assert dataset["ted_modification_chains"] == 10
    assert dataset["gleif_identity_records"] == 5
    assert dataset["questions"] == 50
    assert dataset["question_kinds"] == {
        "relationship_temporal": 35,
        "ordinary_text": 10,
        "no_answer": 5,
    }
    assert dataset["normalized_source_sha256"] == EXPECTED_NORMALIZED_SOURCE_SHA256
    for backfill in dataset["backfills"].values():
        assert backfill["indexed"] > 0


def test_real_retrieval_paths_are_engaged(report):
    sample = report["questions"]["U01-CURRENT"]
    assert sample["A"]["trace"]["vector_signal"] == "disabled"
    assert sample["B"]["trace"]["vector_signal"] == "active"
    assert sample["B"]["trace"]["rerank_signal"] == "active"
    assert sample["C"]["trace"]["vector_signal"] == "active"
    assert sample["C"]["trace"]["rerank_signal"] == "active"
    assert sample["C2"]["trace"]["vector_signal"] == "active"
    assert sample["C2"]["trace"]["rerank_signal"] == "active"


def test_structured_evidence_arm_is_exact_traceable_and_abstains(report):
    arm = report["structured"]["E_structured_plus_evidence"]
    assert arm["relationship_temporal"]["accuracy"] == 1.0
    assert arm["relationship_temporal"]["evidence_traceability"] == 1.0
    assert arm["ordinary_text"]["accuracy"] == 1.0
    assert arm["no_answer"]["no_answer_abstention"] == 1.0


def test_source_native_tools_match_e_without_generic_assertions(report):
    arm = report["alternatives"]["C3_source_native_tools"]
    assert "no generic assertion projection" in arm["model"]
    assert "oracle" in arm["planner"]
    assert arm["all"]["accuracy"] == 1.0
    assert arm["relationship_temporal"]["evidence_traceability"] == 1.0
    assert arm["ordinary_text"]["accuracy"] == 1.0
    assert arm["no_answer"]["no_answer_abstention"] == 1.0
    assert report["decision"]["smaller_alternative_matches_e"] is True


def test_baseline_effect_clears_preregistered_point_and_interval_gate(report):
    effect = report["paired_core_comparison_C2_vs_E"]["bootstrap"]
    assert effect["difference"] >= 0.10
    assert effect["ci95_low"] > 0
    assert report["decision"]["baseline_clears_preregistered_effect_gate"] is True


def test_top_k_sensitivity_prevents_an_overclaim(report):
    sensitivity = report["top_k_sensitivity_C2_vs_E"]
    assert sensitivity["6"]["C2_relationship_temporal"]["oracle_accuracy"] == 0.5714
    assert sensitivity["10"]["C2_relationship_temporal"]["oracle_accuracy"] == 0.8571
    assert sensitivity["15"]["C2_relationship_temporal"]["oracle_accuracy"] == 1.0
    assert sensitivity["15"]["E_minus_C2_bootstrap"]["difference"] == 0.0
    assert report["decision"]["robustness_signal_passed"] is False
    assert report["decision"]["proxy_signal_passed"] is False
    assert report["decision"]["verdict"] == "dont_build_yet"


def test_report_keeps_pilot_limitations_explicit(report):
    limitations = " ".join(report["limitations"]).lower()
    assert "oracle" in limitations
    assert "offline" in limitations
    assert "not a hidden" in limitations
    assert "grant" in limitations
    assert "top-k" in limitations
    assert "oracle intent" in limitations
    assert "f generation is omitted" in limitations
