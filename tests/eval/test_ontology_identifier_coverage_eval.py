"""Public procurement stable-ID coverage and GLEIF mapping evaluation."""

from __future__ import annotations

import csv
from io import BytesIO
from pathlib import Path

import pytest

from scripts.validate_gleif_bulgarian_concat import scan_xml_stream

from tests.eval.ontology_identifier_coverage_harness import (
    EXPECTED_BG_COMMERCIAL_REGISTER_EXTRACT_SHA256,
    EXPECTED_BG_COMMERCIAL_REGISTER_RECORDS_SHA256,
    EXPECTED_BG_GLEIF_CONCATENATED_SCAN_FILE_SHA256,
    EXPECTED_BG_GLEIF_CONCATENATED_SCAN_SUMMARY_SHA256,
    EXPECTED_BG_GLEIF_API_SCAN_SHA256,
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


def test_full_bulgarian_gleif_api_scan_finds_no_target_ids_or_names(identifier_report):
    scan = identifier_report["gleif_bg_api_scan"]
    assert scan["publish_date"] == "2026-10-25T16:00:00Z"
    assert scan["country_filter"] == "BG"
    assert scan["records_enumerated"] == 6222
    assert scan["pages"] == 32
    assert set(scan["target_validated_as_hits"].values()) == {0}
    assert set(scan["target_exact_name_hits"].values()) == {0}
    assert scan["target_match_records"] == {}
    assert scan["summary_sha256"] == EXPECTED_BG_GLEIF_API_SCAN_SHA256
    assert scan["independent_delivery"] is False
    assert identifier_report["decision"]["gleif_bg_api_scan_has_no_target_match"] is True


def test_official_concatenated_file_has_no_target_id_or_exact_name(identifier_report):
    scan = identifier_report["gleif_bulgarian_concatenated_scan"]
    assert scan["source_url"].endswith("/42569/zip")
    assert scan["archive_sha256"] == (
        "23c03705b3f93dd9869af2c9366f1bc191640ac1fd0759e615ff768fc2d09af6"
    )
    assert scan["archive_member"] == "20261025-gleif-concatenated-file-lei2.xml"
    assert scan["xml_content_date"] == "2026-10-25T09:00:01Z"
    assert scan["xml_record_count"] == 3_473_152
    assert scan["records_scanned"] == scan["xml_record_count"]
    assert scan["bg_legal_address_records"] == 6_222
    assert scan["ra000065_records"] == 5_698
    assert all(not hits for hits in scan["target_uic_hits"].values())
    assert all(not hits for hits in scan["target_exact_name_or_alias_hits"].values())
    assert scan["summary_sha256"] == EXPECTED_BG_GLEIF_CONCATENATED_SCAN_SUMMARY_SHA256
    assert scan["extract_sha256"] == EXPECTED_BG_GLEIF_CONCATENATED_SCAN_FILE_SHA256
    assert scan["independent_delivery"] is True
    assert (
        identifier_report["decision"]["gleif_concatenated_scan_has_no_target_match"]
        is True
    )


def test_gleif_concat_parser_uses_header_count_and_scans_aliases():
    xml = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
    <lei:LEIData xmlns:lei=\"http://www.gleif.org/data/schema/leidata/2016\"
      xmlns:gleif=\"http://www.gleif.org/concatenated-file/header-extension/2.0\">
      <lei:LEIHeader><lei:ContentDate>2026-10-25T09:00:01Z</lei:ContentDate>
        <lei:RecordCount>2</lei:RecordCount><lei:Extension><gleif:Sources>
          <gleif:Source><gleif:RecordCount>999</gleif:RecordCount></gleif:Source>
        </gleif:Sources></lei:Extension>
      </lei:LEIHeader><lei:LEIRecords>
        <lei:LEIRecord><lei:LEI>TESTLEI000000000001</lei:LEI><lei:Entity>
          <lei:LegalName>Legal Company</lei:LegalName><lei:OtherEntityNames>
            <lei:OtherEntityName>Target Name</lei:OtherEntityName>
          </lei:OtherEntityNames><lei:LegalAddress><lei:Country>BG</lei:Country>
          </lei:LegalAddress><lei:RegistrationAuthority>
            <lei:RegistrationAuthorityID>RA000065</lei:RegistrationAuthorityID>
            <lei:RegistrationAuthorityEntityID>123456789</lei:RegistrationAuthorityEntityID>
          </lei:RegistrationAuthority></lei:Entity></lei:LEIRecord>
        <lei:LEIRecord><lei:LEI>TESTLEI000000000002</lei:LEI><lei:Entity>
          <lei:LegalName>Other Company</lei:LegalName><lei:LegalAddress>
            <lei:Country>BG</lei:Country></lei:LegalAddress>
          <lei:RegistrationAuthority>
            <lei:RegistrationAuthorityID>RA000066</lei:RegistrationAuthorityID>
            <lei:RegistrationAuthorityEntityID>987654321</lei:RegistrationAuthorityEntityID>
          </lei:RegistrationAuthority></lei:Entity></lei:LEIRecord>
      </lei:LEIRecords></lei:LEIData>"""
    report = scan_xml_stream(
        BytesIO(xml),
        {
            "123456789": {
                "uic": "123456789",
                "ted_name": "Target Name",
                "registry_authority_id": "RA000065",
            }
        },
    )
    assert report["xml_record_count"] == report["records_scanned"] == 2
    assert report["bg_legal_address_records"] == 2
    assert report["ra000065_records"] == 1
    assert report["target_uic_hits"]["123456789"][0]["lei"] == "TESTLEI000000000001"
    assert report["target_exact_name_or_alias_hits"]["123456789"][0]["other_entity_names"] == [
        "Target Name"
    ]


def test_public_identity_adjudication_queue_matches_all_29_orgs(identifier_report):
    queue_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "validation"
        / "ontology-v1"
        / "public-study"
        / "identity_adjudication_queue_v1.csv"
    )
    with queue_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 29
    assert [row["case_id"] for row in rows] == [f"R{index:03}" for index in range(1, 30)]
    assert {row["status"] for row in rows} == {"pending"}
    assert all(not row["reviewer_a_outcome"] for row in rows)
    assert all(not row["reviewer_b_outcome"] for row in rows)
    queue_keys = {
        (row["source_role"], row["source_identifier"], row["source_name"])
        for row in rows
    }
    report_keys = {
        (item["source_role"], item["identifier"], item["name"])
        for item in identifier_report["organizations"]
    }
    assert queue_keys == report_keys


def test_identifier_report_keeps_search_and_namespace_limits_explicit(identifier_report):
    limitations = " ".join(identifier_report["limitations"]).lower()
    assert "lower bound" in limitations
    assert "not an authoritative crosswalk" in limitations
    assert "namespace metadata" in limitations
    assert "raw repeated search-result rows" in limitations
    assert "official eforms xml resolves" in limitations
    assert "multiple gleif registration authorities" in limitations
    assert "commercial register independently confirms" in limitations
    assert "official gleif concatenated" in limitations
    assert "golden copy-based" in limitations
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
