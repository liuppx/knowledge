"""Public procurement stable-ID coverage and GLEIF mapping evaluation."""

from __future__ import annotations

import pytest

from tests.eval.ontology_identifier_coverage_harness import (
    EXPECTED_BG_COMMERCIAL_REGISTER_EXTRACT_SHA256,
    EXPECTED_BG_COMMERCIAL_REGISTER_RECORDS_SHA256,
    EXPECTED_BG_REGISTRATION_AUTHORITIES_SHA256,
    EXPECTED_MAPPING_OBSERVATIONS_SHA256,
    EXPECTED_TED_XML_EXTRACT_SHA256,
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
    assert local["ted_winner_identifier_when_name_published"] == 1.0
    assert local["ted_buyer_chain_stability"] == 1.0
    assert local["ted_buyer_pairing_verified_notices"] == 20
    assert local["ted_winner_search_pairing_verified_notices"] == 5
    assert local["ted_winner_xml_resolved_notices"] == 1
    assert local["ted_winner_xml_resolved"] == 6
    assert local["ted_winner_pairing_verified_notices"] == 6
    assert local["ted_winner_notices_with_names"] == 6
    assert local["ted_winner_unresolved_pairing_notices"] == 0
    assert local["ted_winner_unpaired_identifiers"] == 0
    assert (
        identifier_report["decision"]["source_local_ids_sufficient_for_all_sampled_organizations"]
        is True
    )


def test_cross_source_mapping_does_not_treat_name_candidates_as_authoritative(identifier_report):
    mapping = identifier_report["cross_source_mapping"]
    assert mapping["unique_source_organizations"] == 29
    assert mapping["categories"] == {
        "authoritative_namespace_no_gleif_match_observed": 7,
        "no_exact_gleif_candidate_observed": 19,
        "unique_exact_name_candidate_only": 3,
    }
    assert mapping["authoritative_auto_map_coverage"] == 0.0
    assert mapping["ra000065_authoritative_lei_matches"] == 0
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
    assert organizations[("ted_winner", "МЕТАЛИК АД")]["identifier"] == "833067427"
    assert organizations[("ted_winner", "ВАЛИС ООД")]["identifier"] == "123630361"
    assert organizations[("ted_winner", "МЕТАЛИК АД")]["identifier_country_code"] == "BGR"
    assert (
        organizations[("ted_winner", "МЕТАЛИК АД")]["identifier_namespace_status"]
        == "authoritative_ra000065_confirmed_by_registry"
    )
    assert (
        organizations[("ted_winner", "МЕТАЛИК АД")][
            "gleif_registry_authority_id"
        ]
        == "RA000065"
    )


def test_registry_agency_confirms_namespace_after_xml_restores_pairing(identifier_report):
    xml = identifier_report["ted_xml_resolution"]
    assert xml["extract_sha256"] == EXPECTED_TED_XML_EXTRACT_SHA256
    assert xml["source_xml_sha256"] == (
        "f65386528d46a20f30ca6da69f2df8afcad09d077da0fc2634761932cd0f3f5a"
    )
    assert xml["winner_identifiers_resolved_from_xml"] == 6
    assert xml["organizations_in_frozen_extract"] == 7
    assert xml["company_id_scheme_coverage"] == 0.0
    assert xml["gleif_registration_authorities_sha256"] == (
        EXPECTED_BG_REGISTRATION_AUTHORITIES_SHA256
    )
    assert [
        item["code"] for item in xml["gleif_registration_authority_candidates"]
    ] == ["RA000065", "RA000066", "RA000730", "RA000731"]
    registry = identifier_report["bulgarian_commercial_register_crosswalk"]
    assert registry["registry_authority_id"] == "RA000065"
    assert registry["extract_sha256"] == (
        EXPECTED_BG_COMMERCIAL_REGISTER_EXTRACT_SHA256
    )
    assert registry["records_sha256"] == EXPECTED_BG_COMMERCIAL_REGISTER_RECORDS_SHA256
    assert registry["organizations_checked"] == 7
    assert registry["exact_uic_and_name_matches"] == 7
    assert registry["namespace_coverage"] == 1.0
    assert registry["deed_status_code_counts"] == {1: 1, 2: 6}
    assert {item["uic"] for item in registry["records"]} == {
        "106567752",
        "123018503",
        "123531939",
        "123587426",
        "123630361",
        "202714798",
        "833067427",
    }
    assert identifier_report["decision"]["ted_xml_restores_winner_pairing"] is True
    assert (
        identifier_report["decision"]["ted_company_id_namespace_is_authoritative"]
        is True
    )


def test_identifier_report_keeps_search_and_namespace_limits_explicit(identifier_report):
    limitations = " ".join(identifier_report["limitations"]).lower()
    assert "lower bound" in limitations
    assert "not an authoritative crosswalk" in limitations
    assert "namespace metadata" in limitations
    assert "raw repeated search-result rows" in limitations
    assert "official eforms xml resolves" in limitations
    assert "multiple gleif registration authorities" in limitations
    assert "commercial register independently confirms" in limitations
    assert "cannot estimate" in limitations


def test_frozen_xml_extract_reports_when_official_source_was_not_revalidated(
    monkeypatch, tmp_path
):
    empty_xml_cache = tmp_path / "xml-cache"
    empty_xml_cache.mkdir()
    monkeypatch.setenv("KNOWLEDGE_TED_XML_CACHE_DIR", str(empty_xml_cache))
    report = run_identifier_coverage_eval(report_dir=tmp_path / "reports")
    assert report["ted_xml_resolution"]["source_xml_revalidated"] is False
    assert report["ted_xml_resolution"]["extract_sha256"] == (
        EXPECTED_TED_XML_EXTRACT_SHA256
    )
    assert report["mapping_observations_sha256"] == EXPECTED_MAPPING_OBSERVATIONS_SHA256
