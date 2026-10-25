"""Public procurement stable-ID coverage and GLEIF mapping evaluation."""

from __future__ import annotations

import pytest

from tests.eval.ontology_identifier_coverage_harness import (
    EXPECTED_MAPPING_OBSERVATIONS_SHA256,
    run_identifier_coverage_eval,
)
from tests.eval.ontology_public_dataset import EXPECTED_NORMALIZED_SOURCE_SHA256


pytestmark = pytest.mark.ontology_eval


@pytest.fixture(scope="module")
def identifier_report() -> dict:
    return run_identifier_coverage_eval()


def test_source_local_identifier_coverage_is_measured_without_overclaiming(identifier_report):
    assert identifier_report["normalized_public_source_sha256"] == EXPECTED_NORMALIZED_SOURCE_SHA256
    local = identifier_report["source_local_coverage"]
    assert local["usa_uei_coverage"] == 1.0
    assert local["usa_name_to_multiple_uei"] == 0
    assert local["usa_uei_to_multiple_names"] == 0
    assert local["ted_buyer_identifier_coverage"] == 1.0
    assert local["ted_winner_identifier_when_name_published"] == 0.5385
    assert local["ted_buyer_chain_stability"] == 1.0
    assert local["ted_buyer_pairing_verified_notices"] == 20
    assert local["ted_winner_pairing_verified_notices"] == 5
    assert local["ted_winner_notices_with_names"] == 6
    assert local["ted_winner_unresolved_pairing_notices"] == 1
    assert local["ted_winner_unpaired_identifiers"] == 6
    assert (
        identifier_report["decision"]["source_local_ids_sufficient_for_all_sampled_organizations"]
        is False
    )


def test_cross_source_mapping_does_not_treat_name_candidates_as_authoritative(identifier_report):
    mapping = identifier_report["cross_source_mapping"]
    assert mapping["unique_source_organizations"] == 29
    assert mapping["categories"] == {
        "no_exact_gleif_candidate_observed": 26,
        "unique_exact_name_candidate_only": 3,
    }
    assert mapping["authoritative_auto_map_coverage"] == 0.0
    assert mapping["manual_review_lower_bound"] == 29
    assert identifier_report["mapping_observations_sha256"] == EXPECTED_MAPPING_OBSERVATIONS_SHA256
    assert mapping["manual_review_lower_bound"] >= mapping["categories"].get(
        "unique_exact_name_candidate_only", 0
    )
    assert identifier_report["decision"]["cross_source_lei_mapping_is_automatic"] is False


def test_ted_multi_winner_ids_are_paired_before_deduplication(identifier_report):
    organizations = {
        (item["source_role"], item["name"]): item
        for item in identifier_report["organizations"]
    }
    assert organizations[("ted_winner", 'Sabiedrība ar ierobežotu atbildību "Enersense"')][
        "identifier"
    ] == "50003563201"
    assert organizations[("ted_winner", 'SIA "DEVRE"')]["identifier"] == "44103125989"
    assert organizations[("ted_winner", "МЕТАЛИК АД")]["identifier"] == ""


def test_identifier_report_keeps_search_and_namespace_limits_explicit(identifier_report):
    limitations = " ".join(identifier_report["limitations"]).lower()
    assert "lower bound" in limitations
    assert "not an authoritative crosswalk" in limitations
    assert "namespace metadata" in limitations
    assert "raw repeated search-result rows" in limitations
    assert "unequal flattened winner-name" in limitations
    assert "cannot estimate" in limitations
