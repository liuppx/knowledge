"""Stable-identifier coverage and GLEIF cross-source mapping proxy study."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from tests.eval.ontology_public_harness import (
    DEFAULT_CACHE_DIR,
    DEFAULT_REPORT_DIR,
    TED_FIELDS,
    TED_SEARCH_URL,
    _request_json,
    _sha256_json,
    load_public_records,
)


TED_XML_EXTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "validation"
    / "ontology-v1"
    / "public-study"
    / "ted_xml_organization_extract_v1.json"
)
EXPECTED_TED_XML_EXTRACT_SHA256 = (
    "9616c1381435d1f2032336208756112c99a6885a581cb7445556fa2ae03aacba"
)
EXPECTED_BG_REGISTRATION_AUTHORITIES_SHA256 = (
    "461549fddb62a17e6a07a4f1c985cfeb038953cae185d7328622e477a474d1c7"
)
EXPECTED_MAPPING_OBSERVATIONS_SHA256 = (
    "27ad706210335a3d4ad34ad4d59375bdebfb373b6ab012fe7b27d0e421936110"
)

_XML_NAMESPACES = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
}
_ISO3_TO_ISO2 = {"BGR": "BG"}


def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", str(value or "").casefold(), flags=re.UNICODE))


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _record_has_name(record: dict[str, Any], name: str) -> bool:
    normalized = _normalize_name(name)
    if not normalized:
        return False
    record_names = {
        _normalize_name(record["legal_name"]),
        *(_normalize_name(alias) for alias in record["aliases"]),
    }
    return normalized in record_names


def _parse_ted_xml_organizations(xml_bytes: bytes) -> dict[str, Any]:
    root = ElementTree.fromstring(xml_bytes)
    organizations: dict[str, dict[str, Any]] = {}
    for organization in root.findall(
        ".//efac:Organizations/efac:Organization", _XML_NAMESPACES
    ):
        company = organization.find("efac:Company", _XML_NAMESPACES)
        if company is None:
            continue
        xml_id = company.findtext(
            "cac:PartyIdentification/cbc:ID", namespaces=_XML_NAMESPACES
        )
        company_id = company.find(
            "cac:PartyLegalEntity/cbc:CompanyID", _XML_NAMESPACES
        )
        if not xml_id or company_id is None:
            continue
        organizations[xml_id] = {
            "xml_organization_id": xml_id,
            "name": company.findtext(
                "cac:PartyName/cbc:Name", default="", namespaces=_XML_NAMESPACES
            ),
            "company_id": company_id.text or "",
            "company_id_attributes": dict(sorted(company_id.attrib.items())),
            "country_code": company.findtext(
                "cac:PostalAddress/cac:Country/cbc:IdentificationCode",
                default="",
                namespaces=_XML_NAMESPACES,
            ),
        }

    role_references = {
        "buyer": {
            item.text
            for item in root.findall(
                ".//cac:ContractingParty/cac:Party/cac:PartyIdentification/cbc:ID",
                _XML_NAMESPACES,
            )
            if item.text
        },
        "winner": {
            item.text
            for item in root.findall(
                ".//efac:NoticeResult/efac:TenderingParty/efac:Tenderer/cbc:ID",
                _XML_NAMESPACES,
            )
            if item.text
        },
    }
    selected = []
    for xml_id in sorted(set().union(*role_references.values())):
        item = organizations[xml_id]
        selected.append(
            {
                **item,
                "roles": sorted(
                    role for role, references in role_references.items() if xml_id in references
                ),
            }
        )
    return {
        "notice_id": root.findtext("cbc:ID", default="", namespaces=_XML_NAMESPACES),
        "ubl_customization_id": root.findtext(
            "cbc:CustomizationID", default="", namespaces=_XML_NAMESPACES
        ),
        "organizations": selected,
    }


def _load_ted_xml_extract(cache_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    extract_bytes = TED_XML_EXTRACT_PATH.read_bytes()
    extract_hash = hashlib.sha256(extract_bytes).hexdigest()
    if extract_hash != EXPECTED_TED_XML_EXTRACT_SHA256:
        raise AssertionError(
            "TED XML organization extract drift: expected "
            f"{EXPECTED_TED_XML_EXTRACT_SHA256}, got {extract_hash}"
        )
    extract = json.loads(extract_bytes)
    source = extract["source"]
    xml_cache = Path(
        os.environ.get("KNOWLEDGE_TED_XML_CACHE_DIR", cache_dir / "ted-xml")
    )
    xml_path = xml_cache / f"{source['publication_number']}.xml"
    source_revalidated = False
    if xml_path.exists():
        xml_bytes = xml_path.read_bytes()
        xml_hash = hashlib.sha256(xml_bytes).hexdigest()
        if xml_hash != source["source_xml_sha256"]:
            raise AssertionError(
                "TED source XML drift: expected "
                f"{source['source_xml_sha256']}, got {xml_hash}"
            )
        parsed = _parse_ted_xml_organizations(xml_bytes)
        expected = {
            "notice_id": source["notice_id"],
            "ubl_customization_id": source["ubl_customization_id"],
            "organizations": sorted(
                extract["organizations"], key=lambda item: item["xml_organization_id"]
            ),
        }
        if parsed != expected:
            raise AssertionError("TED XML organization extraction no longer matches frozen gold")
        source_revalidated = True
    return extract, {
        "extract_sha256": extract_hash,
        "source_xml_sha256": source["source_xml_sha256"],
        "source_xml_revalidated": source_revalidated,
        "source_xml_cache_path": str(xml_path),
    }


def _gleif_registration_authorities(
    country_code: str, cache_dir: Path
) -> list[dict[str, Any]]:
    first_query = urllib.parse.urlencode({"page[number]": 1, "page[size]": 100})
    first = _request_json(
        f"https://api.gleif.org/api/v1/registration-authorities?{first_query}",
        cache_dir=cache_dir,
    )
    last_page = first["meta"]["pagination"]["lastPage"]
    responses = [first]
    if last_page > 1:
        urls = []
        for page in range(2, last_page + 1):
            query = urllib.parse.urlencode({"page[number]": page, "page[size]": 100})
            urls.append(f"https://api.gleif.org/api/v1/registration-authorities?{query}")
        with ThreadPoolExecutor(max_workers=6) as executor:
            responses.extend(
                executor.map(lambda url: _request_json(url, cache_dir=cache_dir), urls)
            )

    authorities = []
    for response in responses:
        for item in response["data"]:
            attributes = item["attributes"]
            jurisdictions = attributes.get("jurisdictions", [])
            if not any(entry.get("countryCode") == country_code for entry in jurisdictions):
                continue
            authorities.append(
                {
                    "code": attributes["code"],
                    "international_name": attributes.get("internationalName"),
                    "local_name": attributes.get("localName"),
                    "international_organization_name": attributes.get(
                        "internationalOrganizationName"
                    ),
                    "local_organization_name": attributes.get("localOrganizationName"),
                    "jurisdictions": sorted(
                        jurisdictions,
                        key=lambda entry: (
                            entry.get("countryCode", ""),
                            entry.get("jurisdiction", ""),
                        ),
                    ),
                }
            )
    return sorted(authorities, key=lambda item: item["code"])


def _gleif_search(
    *,
    filter_name: str,
    value: str,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({filter_name: value, "page[size]": 100})
    response = _request_json(
        f"https://api.gleif.org/api/v1/lei-records?{query}",
        cache_dir=cache_dir,
    )
    records = []
    for item in response.get("data", []):
        attributes = item["attributes"]
        entity = attributes["entity"]
        registration = attributes["registration"]
        records.append(
            {
                "lei": attributes["lei"],
                "legal_name": entity["legalName"]["name"],
                "aliases": sorted(item["name"] for item in entity.get("otherNames", [])),
                "registry_authority_id": registration.get("validatedAt", {}).get("id", ""),
                "registry_entity_id": registration.get("validatedAs") or "",
                "registration_status": registration["status"],
            }
        )
    return sorted(records, key=lambda item: (item["lei"], item["legal_name"]))


def _single_language_rows(value: Any, *, notice_id: str, field: str) -> list[str]:
    if not isinstance(value, dict):
        return []
    populated = []
    for language, entries in value.items():
        rows = entries if isinstance(entries, list) else [entries]
        normalized = [str(entry) for entry in rows if entry]
        if normalized:
            populated.append((language, normalized))
    if len(populated) > 1:
        raise AssertionError(
            f"cannot prove positional {field} pairing across languages for {notice_id}: "
            f"{[language for language, _ in populated]}"
        )
    return populated[0][1] if populated else []


def _fetch_ted_organization_observations(
    notice_id: str, cache_dir: Path
) -> dict[str, dict[str, Any]]:
    response = _request_json(
        TED_SEARCH_URL,
        payload={
            "query": f'notice-identifier = "{notice_id}"',
            "fields": TED_FIELDS,
            "page": 1,
            "limit": 5,
            "scope": "ALL",
            "onlyLatestVersions": False,
        },
        cache_dir=cache_dir,
    )
    if len(response.get("notices", [])) != 1:
        raise AssertionError(f"expected one TED notice for organization pairing: {notice_id}")
    notice = response["notices"][0]
    result: dict[str, dict[str, Any]] = {}
    for role in ("buyer", "winner"):
        names = _single_language_rows(
            notice.get(f"{role}-name"), notice_id=notice_id, field=f"{role} name/identifier"
        )
        identifiers = [str(value) for value in notice.get(f"{role}-identifier", []) if value]
        pairing_verified = len(names) == len(identifiers)
        if pairing_verified:
            pairs = sorted(set(zip(names, identifiers)))
            organizations = [
                {"name": name, "identifier": identifier} for name, identifier in pairs
            ]
        else:
            organizations = [
                {"name": name, "identifier": ""} for name in sorted(set(names))
            ]
        result[role] = {
            "organizations": organizations,
            "pairing_verified": pairing_verified,
            "search_pairing_verified": pairing_verified,
            "xml_resolved": 0,
            "published_names": len(set(names)),
            "published_identifiers": len(set(identifiers)),
            "published_identifier_values": sorted(set(identifiers)),
        }
    return result


def _resolve_ted_observations_with_xml(
    notice_id: str,
    observations: dict[str, dict[str, Any]],
    xml_extract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    for result in observations.values():
        result["organizations"] = [
            {
                **item,
                "identifier_country_code": None,
                "identifier_namespace_status": "not_exposed_by_ted_search",
                "identifier_evidence": "TED Search API raw rows",
            }
            for item in result["organizations"]
        ]
    if notice_id != xml_extract["source"]["notice_id"]:
        return observations

    for role in ("buyer", "winner"):
        result = observations[role]
        xml_organizations = sorted(
            (
                item
                for item in xml_extract["organizations"]
                if role in item["roles"]
            ),
            key=lambda item: item["name"],
        )
        xml_names = {item["name"] for item in xml_organizations}
        search_names = {item["name"] for item in result["organizations"]}
        xml_identifiers = {item["company_id"] for item in xml_organizations}
        search_identifiers = set(result["published_identifier_values"])
        if xml_names != search_names or xml_identifiers != search_identifiers:
            raise AssertionError(
                f"TED XML does not reconcile flattened {role} fields for {notice_id}"
            )
        result["organizations"] = [
            {
                "name": item["name"],
                "identifier": item["company_id"],
                "identifier_country_code": item["country_code"],
                "identifier_namespace_status": (
                    "scheme_declared_in_ted_xml"
                    if item["company_id_attributes"]
                    else "country_only_scheme_absent_in_ted_xml"
                ),
                "identifier_evidence": "TED eForms XML organization node",
            }
            for item in xml_organizations
        ]
        result["xml_resolved"] = (
            0 if result["search_pairing_verified"] else len(xml_organizations)
        )
        result["pairing_verified"] = True
    return observations


def _collect_organizations(
    data: dict[str, Any], cache_dir: Path, xml_extract: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    organizations: dict[tuple[str, str, str], dict[str, Any]] = {}
    usa_name_to_ids: dict[str, set[str]] = defaultdict(set)
    usa_id_to_names: dict[str, set[str]] = defaultdict(set)
    for award in data["usa"]:
        name = award["recipient_name"]
        identifier = award["recipient_uei"]
        key = ("usa_recipient", name, identifier)
        organizations.setdefault(
            key,
            {
                "source_role": "usa_recipient",
                "name": name,
                "identifier": identifier,
                "identifier_type": "UEI",
                "identifier_namespace": "US-SAM-UEI",
                "identifier_country_code": None,
                "identifier_namespace_status": "known_source_namespace",
                "identifier_evidence": "USAspending award recipient record",
                "gleif_registry_authority_id": None,
                "occurrences": 0,
            },
        )["occurrences"] += 1
        usa_name_to_ids[name].add(identifier)
        usa_id_to_names[identifier].add(name)

    ted_buyer_observations = 0
    ted_buyer_identified = 0
    ted_winner_names = 0
    ted_winner_identified = 0
    stable_buyer_chains = 0
    ted_buyer_pairing_verified_notices = 0
    ted_winner_notices_with_names = 0
    ted_winner_pairing_verified_notices = 0
    ted_winner_search_pairing_verified_notices = 0
    ted_winner_xml_resolved_notices = 0
    ted_winner_xml_resolved = 0
    ted_winner_unresolved_pairing_notices = 0
    ted_winner_unpaired_identifiers = 0
    for pair in data["ted"]:
        current = pair["current"]
        previous = pair["previous"]
        if set(current["buyer_ids"]) == set(previous["buyer_ids"]):
            stable_buyer_chains += 1
        for notice in (current, previous):
            observations = _resolve_ted_observations_with_xml(
                notice["notice_id"],
                _fetch_ted_organization_observations(notice["notice_id"], cache_dir),
                xml_extract,
            )
            buyer_result = observations["buyer"]
            winner_result = observations["winner"]
            buyer_pairs = buyer_result["organizations"]
            winner_pairs = winner_result["organizations"]
            ted_buyer_pairing_verified_notices += int(buyer_result["pairing_verified"])
            ted_buyer_observations += buyer_result["published_names"]
            ted_buyer_identified += sum(bool(item["identifier"]) for item in buyer_pairs)
            if winner_result["published_names"]:
                ted_winner_notices_with_names += 1
                ted_winner_pairing_verified_notices += int(winner_result["pairing_verified"])
                ted_winner_search_pairing_verified_notices += int(
                    winner_result["search_pairing_verified"]
                )
                ted_winner_xml_resolved_notices += int(winner_result["xml_resolved"] > 0)
                ted_winner_unresolved_pairing_notices += int(
                    not winner_result["pairing_verified"]
                )
            ted_winner_xml_resolved += winner_result["xml_resolved"]
            ted_winner_unpaired_identifiers += (
                0
                if winner_result["pairing_verified"]
                else winner_result["published_identifiers"]
            )
            ted_winner_names += winner_result["published_names"]
            ted_winner_identified += sum(bool(item["identifier"]) for item in winner_pairs)
            for item in buyer_pairs:
                name = item["name"]
                identifier = item["identifier"]
                key = ("ted_buyer", name, identifier)
                organizations.setdefault(
                    key,
                    {
                        "source_role": "ted_buyer",
                        "name": name,
                        "identifier": identifier,
                        "identifier_type": "TED buyer identifier",
                        "identifier_namespace": "unresolved TED organization namespace",
                        "identifier_country_code": item["identifier_country_code"],
                        "identifier_namespace_status": item[
                            "identifier_namespace_status"
                        ],
                        "identifier_evidence": item["identifier_evidence"],
                        "gleif_registry_authority_id": None,
                        "occurrences": 0,
                    },
                )
                organizations[key]["occurrences"] += 1
                if item["identifier_evidence"].startswith("TED eForms XML"):
                    organizations[key].update(
                        {
                            "identifier_country_code": item[
                                "identifier_country_code"
                            ],
                            "identifier_namespace_status": item[
                                "identifier_namespace_status"
                            ],
                            "identifier_evidence": item["identifier_evidence"],
                        }
                    )
            for item in winner_pairs:
                name = item["name"]
                identifier = item["identifier"]
                key = ("ted_winner", name, identifier)
                organizations.setdefault(
                    key,
                    {
                        "source_role": "ted_winner",
                        "name": name,
                        "identifier": identifier,
                        "identifier_type": "TED winner identifier",
                        "identifier_namespace": "unresolved TED organization namespace",
                        "identifier_country_code": item["identifier_country_code"],
                        "identifier_namespace_status": item[
                            "identifier_namespace_status"
                        ],
                        "identifier_evidence": item["identifier_evidence"],
                        "gleif_registry_authority_id": None,
                        "occurrences": 0,
                    },
                )["occurrences"] += 1

    coverage = {
        "usa_awards": len(data["usa"]),
        "usa_awards_with_uei": sum(bool(award["recipient_uei"]) for award in data["usa"]),
        "usa_unique_recipients": len(usa_name_to_ids),
        "usa_name_to_multiple_uei": sum(len(ids) > 1 for ids in usa_name_to_ids.values()),
        "usa_uei_to_multiple_names": sum(len(names) > 1 for names in usa_id_to_names.values()),
        "ted_chains": len(data["ted"]),
        "ted_buyer_stable_chains": stable_buyer_chains,
        "ted_buyer_observations": ted_buyer_observations,
        "ted_buyer_identified": ted_buyer_identified,
        "ted_winner_names_published": ted_winner_names,
        "ted_winner_identified": ted_winner_identified,
        "ted_buyer_pairing_verified_notices": ted_buyer_pairing_verified_notices,
        "ted_winner_notices_with_names": ted_winner_notices_with_names,
        "ted_winner_pairing_verified_notices": ted_winner_pairing_verified_notices,
        "ted_winner_search_pairing_verified_notices": (
            ted_winner_search_pairing_verified_notices
        ),
        "ted_winner_xml_resolved_notices": ted_winner_xml_resolved_notices,
        "ted_winner_xml_resolved": ted_winner_xml_resolved,
        "ted_winner_unresolved_pairing_notices": ted_winner_unresolved_pairing_notices,
        "ted_winner_unpaired_identifiers": ted_winner_unpaired_identifiers,
        "ted_xml_organizations": len(xml_extract["organizations"]),
        "ted_xml_company_ids_with_declared_scheme": sum(
            bool(item["company_id_attributes"])
            for item in xml_extract["organizations"]
        ),
    }
    ordered = sorted(
        organizations.values(), key=lambda item: (item["source_role"], item["name"])
    )
    return ordered, coverage


def _map_organization(organization: dict[str, Any], cache_dir: Path) -> dict[str, Any]:
    identifier = organization["identifier"]
    name = organization["name"]
    direct_results = (
        _gleif_search(
            filter_name="filter[registration.validatedAs]",
            value=identifier,
            cache_dir=cache_dir,
        )
        if identifier
        else []
    )
    unscoped_direct_matches = [
        record
        for record in direct_results
        if _normalize_identifier(record["registry_entity_id"]) == _normalize_identifier(identifier)
    ]
    expected_authority = organization["gleif_registry_authority_id"]
    direct_matches = [
        record
        for record in unscoped_direct_matches
        if expected_authority and record["registry_authority_id"] == expected_authority
    ]
    direct_name_matches = [
        record for record in direct_matches if _record_has_name(record, name)
    ]
    if len(direct_name_matches) == 1:
        category = "authoritative_id_and_name"
    elif len(direct_matches) == 1:
        category = "authoritative_id_name_mismatch"
    elif len(direct_matches) > 1:
        category = "authoritative_id_ambiguous"
    else:
        unscoped_name_matches = [
            record for record in unscoped_direct_matches if _record_has_name(record, name)
        ]
        if len(unscoped_name_matches) == 1:
            category = "registry_id_and_name_candidate_missing_namespace"
            direct_name_matches = unscoped_name_matches
            return {
                **organization,
                "mapping_category": category,
                "candidates": direct_name_matches,
            }
        if len(unscoped_name_matches) > 1:
            category = "ambiguous_registry_id_and_name_candidates_missing_namespace"
            direct_name_matches = unscoped_name_matches
            return {
                **organization,
                "mapping_category": category,
                "candidates": direct_name_matches,
            }
        if len(unscoped_direct_matches) == 1:
            return {
                **organization,
                "mapping_category": "registry_id_candidate_name_mismatch_missing_namespace",
                "candidates": unscoped_direct_matches,
            }
        if len(unscoped_direct_matches) > 1:
            return {
                **organization,
                "mapping_category": "ambiguous_registry_id_candidates_missing_namespace",
                "candidates": unscoped_direct_matches,
            }
        name_results = _gleif_search(
            filter_name="filter[entity.names]",
            value=name,
            cache_dir=cache_dir,
        )
        exact_name_matches = [
            record for record in name_results if _record_has_name(record, name)
        ]
        if len(exact_name_matches) == 1:
            category = "unique_exact_name_candidate_only"
        elif len(exact_name_matches) > 1:
            category = "ambiguous_exact_name_candidates"
        else:
            category = "no_exact_gleif_candidate_observed"
        direct_name_matches = exact_name_matches
    return {
        **organization,
        "mapping_category": category,
        "candidates": direct_name_matches if direct_name_matches else direct_matches,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / (denominator or 1), 4)


def run_identifier_coverage_eval(
    report_dir: Path | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    selected_cache = cache_dir or Path(
        os.environ.get("KNOWLEDGE_ONTOLOGY_EVAL_CACHE_DIR", DEFAULT_CACHE_DIR)
    )
    data = load_public_records(selected_cache)
    xml_extract, xml_validation = _load_ted_xml_extract(selected_cache)
    organizations, coverage = _collect_organizations(data, selected_cache, xml_extract)
    xml_country_codes = sorted(
        {item["country_code"] for item in xml_extract["organizations"]}
    )
    if xml_country_codes != ["BGR"]:
        raise AssertionError(f"unexpected TED XML country codes: {xml_country_codes}")
    gleif_country_code = _ISO3_TO_ISO2[xml_country_codes[0]]
    registration_authorities = _gleif_registration_authorities(
        gleif_country_code, selected_cache
    )
    registration_authorities_hash = _sha256_json(registration_authorities)
    if registration_authorities_hash != EXPECTED_BG_REGISTRATION_AUTHORITIES_SHA256:
        raise AssertionError(
            "GLEIF Bulgarian registration-authority drift: expected "
            f"{EXPECTED_BG_REGISTRATION_AUTHORITIES_SHA256}, "
            f"got {registration_authorities_hash}"
        )
    with ThreadPoolExecutor(max_workers=6) as executor:
        mappings = list(
            executor.map(lambda org: _map_organization(org, selected_cache), organizations)
        )
    categories = Counter(mapping["mapping_category"] for mapping in mappings)
    authoritative = categories["authoritative_id_and_name"]
    manual_review = len(mappings) - authoritative
    mapping_hash = _sha256_json(mappings)
    if mapping_hash != EXPECTED_MAPPING_OBSERVATIONS_SHA256:
        raise AssertionError(
            "GLEIF mapping observation drift: expected "
            f"{EXPECTED_MAPPING_OBSERVATIONS_SHA256}, got {mapping_hash}"
        )
    report = {
        "normalized_public_source_sha256": _sha256_json(data),
        "mapping_observations_sha256": mapping_hash,
        "ted_xml_resolution": {
            **xml_validation,
            "source_notice_id": xml_extract["source"]["notice_id"],
            "source_publication_number": xml_extract["source"][
                "publication_number"
            ],
            "winner_identifiers_resolved_from_xml": coverage[
                "ted_winner_xml_resolved"
            ],
            "organizations_in_frozen_extract": coverage["ted_xml_organizations"],
            "company_ids_with_declared_scheme": coverage[
                "ted_xml_company_ids_with_declared_scheme"
            ],
            "company_id_scheme_coverage": _ratio(
                coverage["ted_xml_company_ids_with_declared_scheme"],
                coverage["ted_xml_organizations"],
            ),
            "country_codes": xml_country_codes,
            "gleif_country_code": gleif_country_code,
            "gleif_registration_authorities_sha256": (
                registration_authorities_hash
            ),
            "gleif_registration_authority_candidates": registration_authorities,
            "gleif_registration_authority_candidate_count": len(
                registration_authorities
            ),
        },
        "source_local_coverage": {
            **coverage,
            "usa_uei_coverage": _ratio(coverage["usa_awards_with_uei"], coverage["usa_awards"]),
            "ted_buyer_identifier_coverage": _ratio(
                coverage["ted_buyer_identified"], coverage["ted_buyer_observations"]
            ),
            "ted_winner_identifier_when_name_published": _ratio(
                coverage["ted_winner_identified"], coverage["ted_winner_names_published"]
            ),
            "ted_buyer_chain_stability": _ratio(
                coverage["ted_buyer_stable_chains"], coverage["ted_chains"]
            ),
        },
        "cross_source_mapping": {
            "unique_source_organizations": len(mappings),
            "categories": dict(sorted(categories.items())),
            "authoritative_auto_map_coverage": _ratio(authoritative, len(mappings)),
            "manual_review_lower_bound": manual_review,
            "manual_review_rate_lower_bound": _ratio(manual_review, len(mappings)),
        },
        "decision": {
            "source_local_ids_sufficient_for_all_sampled_organizations": (
                coverage["usa_awards_with_uei"] == coverage["usa_awards"]
                and coverage["ted_buyer_identified"] == coverage["ted_buyer_observations"]
                and coverage["ted_winner_identified"] == coverage["ted_winner_names_published"]
                and coverage["ted_buyer_stable_chains"] == coverage["ted_chains"]
            ),
            "cross_source_lei_mapping_is_automatic": authoritative == len(mappings),
            "ted_xml_restores_winner_pairing": (
                coverage["ted_winner_identified"]
                == coverage["ted_winner_names_published"]
            ),
            "ted_company_id_namespace_is_authoritative": (
                coverage["ted_xml_company_ids_with_declared_scheme"]
                == coverage["ted_xml_organizations"]
                and len(registration_authorities) == 1
            ),
            "verdict": "keep_source_ids; review_cross_source_candidates; do_not_auto_merge",
        },
        "limitations": [
            (
                "GLEIF exact-name search is an observed candidate lower bound, not proof "
                "that an organization has no LEI."
            ),
            (
                "A unique exact-name candidate without a matching registry identifier is "
                "not an authoritative crosswalk."
            ),
            (
                "TED identifiers include national identifiers and platform UUIDs; namespace "
                "metadata is required before cross-source use."
            ),
            (
                "TED organization names and identifiers are paired on raw repeated "
                "search-result rows before deduplication; independently deduplicated arrays "
                "cannot prove identity."
            ),
            (
                "One sampled TED notice publishes unequal flattened winner-name and "
                "winner-identifier row counts; its official eForms XML resolves the six "
                "pairs through organization references."
            ),
            (
                "The sampled TED XML CompanyID elements have no scheme attribute, and "
                "country BGR maps to multiple GLEIF registration authorities; the XML "
                "therefore restores source-local pairing but not an authoritative namespace."
            ),
            (
                "The sample deliberately contains modification chains and cannot estimate "
                "organization-ID coverage for all procurement records."
            ),
        ],
        "organizations": mappings,
    }
    destination = report_dir or Path(
        os.environ.get("KNOWLEDGE_EVAL_REPORT_DIR", DEFAULT_REPORT_DIR)
    )
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "ontology_identifier_coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (destination / "ontology_identifier_coverage.md").write_text(
        render_identifier_coverage_markdown(report), encoding="utf-8"
    )
    return report


def render_identifier_coverage_markdown(report: dict[str, Any]) -> str:
    local = report["source_local_coverage"]
    mapping = report["cross_source_mapping"]
    xml = report["ted_xml_resolution"]
    lines = [
        "## Procurement stable-identifier coverage",
        "",
        f"- USAspending UEI coverage: {local['usa_uei_coverage']:.1%}",
        f"- TED buyer identifier coverage: {local['ted_buyer_identifier_coverage']:.1%}",
        "- TED winner ID when winner name is published: "
        f"{local['ted_winner_identifier_when_name_published']:.1%}",
        "- TED buyer ID stability across modification chains: "
        f"{local['ted_buyer_chain_stability']:.1%}",
        f"- TED winner notices with verified raw-row pairing: "
        f"{local['ted_winner_search_pairing_verified_notices']}/"
        f"{local['ted_winner_notices_with_names']}",
        "- TED winner IDs resolved from official XML: "
        f"{local['ted_winner_xml_resolved']}",
        "- TED winner pairing after XML resolution: "
        f"{local['ted_winner_pairing_verified_notices']}/"
        f"{local['ted_winner_notices_with_names']}",
        "- TED winner notices with unresolved pairing: "
        f"{local['ted_winner_unresolved_pairing_notices']}",
        f"- TED XML extract SHA-256: `{xml['extract_sha256']}`",
        f"- TED source XML SHA-256: `{xml['source_xml_sha256']}`",
        f"- TED source XML revalidated this run: {xml['source_xml_revalidated']}",
        f"- TED XML CompanyID scheme coverage: {xml['company_id_scheme_coverage']:.1%}",
        "- GLEIF registration-authority candidates for BGR: "
        f"{xml['gleif_registration_authority_candidate_count']}",
        "",
        f"- unique source organizations: {mapping['unique_source_organizations']}",
        f"- mapping categories: `{mapping['categories']}`",
        f"- mapping observations SHA-256: `{report['mapping_observations_sha256']}`",
        f"- authoritative LEI auto-map coverage: {mapping['authoritative_auto_map_coverage']:.1%}",
        f"- manual-review lower bound: {mapping['manual_review_lower_bound']} "
        f"({mapping['manual_review_rate_lower_bound']:.1%})",
        f"- verdict: `{report['decision']['verdict']}`",
        "",
    ]
    return "\n".join(lines)
