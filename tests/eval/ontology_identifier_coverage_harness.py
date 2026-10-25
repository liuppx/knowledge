"""Stable-identifier coverage and GLEIF cross-source mapping proxy study."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from tests.eval.ontology_public_harness import (
    DEFAULT_CACHE_DIR,
    DEFAULT_REPORT_DIR,
    TED_FIELDS,
    TED_SEARCH_URL,
    _request_json,
    _sha256_json,
    load_public_records,
)


EXPECTED_MAPPING_OBSERVATIONS_SHA256 = (
    "04fa671c96763da0fe5f8388f177f34523f216f8e0d7b6c9a14de07ff7cdfa23"
)


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
            "published_names": len(set(names)),
            "published_identifiers": len(set(identifiers)),
        }
    return result


def _collect_organizations(
    data: dict[str, Any], cache_dir: Path
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
    ted_winner_unresolved_pairing_notices = 0
    ted_winner_unpaired_identifiers = 0
    for pair in data["ted"]:
        current = pair["current"]
        previous = pair["previous"]
        if set(current["buyer_ids"]) == set(previous["buyer_ids"]):
            stable_buyer_chains += 1
        for notice in (current, previous):
            observations = _fetch_ted_organization_observations(
                notice["notice_id"], cache_dir
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
                ted_winner_unresolved_pairing_notices += int(
                    not winner_result["pairing_verified"]
                )
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
                        "gleif_registry_authority_id": None,
                        "occurrences": 0,
                    },
                )["occurrences"] += 1
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
        "ted_winner_unresolved_pairing_notices": ted_winner_unresolved_pairing_notices,
        "ted_winner_unpaired_identifiers": ted_winner_unpaired_identifiers,
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
    organizations, coverage = _collect_organizations(data, selected_cache)
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
                "winner-identifier row counts, so six winner IDs remain unpaired until the "
                "source XML or another authoritative organization structure is resolved."
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
        f"{local['ted_winner_pairing_verified_notices']}/{local['ted_winner_notices_with_names']}",
        "- TED winner notices with unresolved pairing: "
        f"{local['ted_winner_unresolved_pairing_notices']}",
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
