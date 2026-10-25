"""Frozen natural-language planner challenge for the C3 source-native tools."""

from __future__ import annotations

import pytest

from tests.eval.ontology_planner import DeterministicSourcePlanner
from tests.eval.ontology_planner_harness import (
    EXPECTED_CHALLENGE_SHA256,
    run_planner_challenge,
)


pytestmark = pytest.mark.ontology_eval


@pytest.fixture(scope="module")
def planner_report() -> dict:
    return run_planner_challenge()


def test_challenge_is_frozen_and_split_before_planner(planner_report):
    assert planner_report["challenge_sha256"] == EXPECTED_CHALLENGE_SHA256
    assert planner_report["metrics"]["development"]["cases"] == 12
    assert planner_report["metrics"]["test"]["cases"] == 30
    assert planner_report["metrics"]["test"]["answer_cases"] == 23
    assert planner_report["metrics"]["test"]["abstain_cases"] == 7


def test_planner_clears_frozen_test_thresholds(planner_report):
    assert planner_report["passed"] is True
    assert all(planner_report["gates"].values())


def test_planner_never_merges_negative_or_ambiguous_cases(planner_report):
    metrics = planner_report["metrics"]["test"]
    assert metrics["abstention"] == 1.0
    assert metrics["false_merge_count"] == 0
    for case_id in ("T24", "T25", "T26", "T27", "T28", "T29", "T30"):
        assert planner_report["cases"][case_id]["planner"]["status"] == "abstain"


def test_planner_plus_c3_answers_and_evidence_clear_gates(planner_report):
    metrics = planner_report["metrics"]["test"]
    assert metrics["end_to_end_answer_accuracy"] >= 0.90
    assert metrics["evidence_traceability"] == 1.0


def test_report_does_not_mislabel_the_challenge_as_hidden(planner_report):
    limitations = " ".join(planner_report["limitations"]).lower()
    assert "not an externally held hidden set" in limitations
    assert "not a live model-quality result" in limitations


def test_stable_award_identifier_overrides_an_ambiguous_recipient_name():
    data = {
        "usa": [
            {"award_id": "CONT_AWD_A1_0001", "piid": "A1", "recipient_name": "ACME CORP"},
            {"award_id": "CONT_AWD_A2_0001", "piid": "A2", "recipient_name": "ACME CORP"},
        ],
        "ted": [],
        "gleif": [],
    }
    result = DeterministicSourcePlanner(data).plan(
        "ACME CORP 的 Award A1 当前累计 obligation 是多少？"
    )
    assert result["status"] == "planned"
    assert result["operation"] == "usa_latest_total"
    assert result["params"] == {"award_id": "CONT_AWD_A1_0001"}
    assert result["identifier_kind"] == "piid"
