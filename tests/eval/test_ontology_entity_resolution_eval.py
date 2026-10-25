"""GLEIF-backed entity-resolution proxy evaluation."""

from __future__ import annotations

import pytest

from tests.eval.ontology_entity_resolution_harness import (
    EXPECTED_GLEIF_SOURCE_SHA256,
    EXPECTED_PAIR_SHA256,
    run_entity_resolution_eval,
)


pytestmark = pytest.mark.ontology_eval


@pytest.fixture(scope="module")
def entity_report() -> dict:
    return run_entity_resolution_eval()


def test_entity_pair_gold_is_frozen_and_official(entity_report):
    assert entity_report["pair_sha256"] == EXPECTED_PAIR_SHA256
    assert entity_report["dataset"] == {
        "pairs": 22,
        "same": 7,
        "different": 15,
        "unique_leis": 20,
        "all_registration_statuses": ["ISSUED"],
    }
    assert entity_report["normalized_gleif_source_sha256"] == EXPECTED_GLEIF_SOURCE_SHA256


def test_name_similarity_has_no_threshold_that_clears_h4(entity_report):
    assert entity_report["decision"]["any_name_only_threshold_meets_h4"] is False
    for method in entity_report["name_only_methods"].values():
        assert method["ranking_inversion"] is True
        assert method["max_negative_score"] > method["min_positive_score"]
        assert method["qualifying_thresholds"] == []


def test_authoritative_crosswalk_clears_identity_targets_without_false_merge(entity_report):
    crosswalk = entity_report["authoritative_alias_to_lei_crosswalk"]
    assert crosswalk["precision"] == 1.0
    assert crosswalk["recall"] == 1.0
    assert crosswalk["false_merge_rate"] == 0.0
    assert crosswalk["uncertain"] == 0
    assert entity_report["decision"]["crosswalk_meets_h4"] is True


def test_entity_report_keeps_sampling_limitations_explicit(entity_report):
    limitations = " ".join(entity_report["limitations"]).lower()
    assert "do not estimate population prevalence" in limitations
    assert "upper bound" in limitations
    assert "counterexamples" in limitations
