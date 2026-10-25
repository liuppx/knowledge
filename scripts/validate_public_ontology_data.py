#!/usr/bin/env python3
"""Validate public proxy data for the ontology V1 research protocol.

This script intentionally does not ingest data into Knowledge or claim product-market
validation. It checks whether immutable public benchmarks and official public APIs can
support reproducible tests of Evidence locators, temporal modifications, business
object identity, and contract-product-organization relationships.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile


USER_AGENT = "Knowledge-public-ontology-validation/1.0"

CONTRACT_NLI_URL = (
    "https://raw.githubusercontent.com/stanfordnlp/contract-nli/"
    "eced6528dd3c1d14d73f9a87df8f7bdbc03126f9/resources/contract-nli.zip"
)
CONTRACT_NLI_SHA256 = "e03fc77bbf8b53e2976a250e81d8a294bc3d5e5fb014521e477dee9340d6287b"

CUAD_URL = (
    "https://raw.githubusercontent.com/The-Atticus-Project/cuad/"
    "67faa0e6023b04fcaae6cc09497ab00e5d63a2a2/data.zip"
)
CUAD_SHA256 = "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a"

USASPENDING_AWARD_ID = "CONT_AWD_ZN31_9700_W91QUZ06D0004_9700"
TED_CURRENT_NOTICE_ID = "0d4b759d-089c-4b8b-97f0-91276cb03ce6"
TED_PREVIOUS_NOTICE_ID = "ba7a1185-4e7d-4c71-a1bb-6f2099127aa5"
GLEIF_HP_LEI = "WHKXQACZ14C5XRO8LW03"


class ValidationError(RuntimeError):
    pass


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
    data = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ValidationError(f"failed to read JSON from {url}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_download(url: str, expected_sha256: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        actual = _sha256_file(destination)
        if actual != expected_sha256:
            raise ValidationError(
                f"cached file has unexpected checksum: {destination}; "
                f"expected {expected_sha256}, got {actual}"
            )
        return destination

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
    except urllib.error.URLError as exc:
        raise ValidationError(f"failed to download {url}: {exc}") from exc

    actual = _sha256_file(temporary)
    if actual != expected_sha256:
        raise ValidationError(
            f"download checksum mismatch for {url}; expected {expected_sha256}, got {actual}"
        )
    temporary.replace(destination)
    return destination


def analyze_contract_nli(path: Path) -> dict[str, Any]:
    document_count = 0
    document_ids: list[Any] = []
    document_types: Counter[str] = Counter()
    choices: Counter[str] = Counter()
    evidence_annotations = 0
    evidence_span_references = 0
    integrity_errors: list[dict[str, Any]] = []
    split_counts: dict[str, int] = {}
    label_count = 0

    with ZipFile(path) as archive:
        for split in ("train", "dev", "test"):
            data = json.loads(archive.read(f"contract-nli/{split}.json"))
            documents = data["documents"]
            labels = data["labels"]
            split_counts[split] = len(documents)
            label_count = len(labels)
            document_count += len(documents)

            for document in documents:
                document_ids.append(document["id"])
                document_types[document["document_type"]] += 1
                text = document["text"]
                spans = document["spans"]
                for index, (start, end) in enumerate(spans):
                    if not 0 <= start < end <= len(text):
                        integrity_errors.append(
                            {"document_id": document["id"], "span_index": index, "error": "range"}
                        )

                annotations = document["annotation_sets"][0]["annotations"]
                if set(annotations) != set(labels):
                    integrity_errors.append(
                        {"document_id": document["id"], "error": "label_set_mismatch"}
                    )
                for label_id, annotation in annotations.items():
                    choice = annotation["choice"]
                    evidence = annotation["spans"]
                    choices[choice] += 1
                    if choice == "NotMentioned":
                        if evidence:
                            integrity_errors.append(
                                {
                                    "document_id": document["id"],
                                    "label_id": label_id,
                                    "error": "not_mentioned_has_evidence",
                                }
                            )
                    else:
                        evidence_annotations += 1
                        evidence_span_references += len(evidence)
                        if not evidence:
                            integrity_errors.append(
                                {
                                    "document_id": document["id"],
                                    "label_id": label_id,
                                    "error": "decision_missing_evidence",
                                }
                            )
                    for span_index in evidence:
                        if not 0 <= span_index < len(spans):
                            integrity_errors.append(
                                {
                                    "document_id": document["id"],
                                    "label_id": label_id,
                                    "span_index": span_index,
                                    "error": "evidence_index",
                                }
                            )

    return {
        "source_url": CONTRACT_NLI_URL,
        "license": "CC BY 4.0",
        "sha256": _sha256_file(path),
        "documents": document_count,
        "unique_document_ids": len(set(document_ids)),
        "splits": split_counts,
        "hypotheses": label_count,
        "annotations": sum(choices.values()),
        "choices": dict(sorted(choices.items())),
        "document_types": dict(sorted(document_types.items())),
        "sec_origin_documents": document_types["sec-text"] + document_types["sec-html"],
        "evidence_annotations": evidence_annotations,
        "evidence_span_references": evidence_span_references,
        "integrity_error_count": len(integrity_errors),
        "checks": {
            "all_document_ids_unique": len(document_ids) == len(set(document_ids)),
            "annotation_matrix_complete": sum(choices.values()) == document_count * label_count,
            "all_non_neutral_decisions_have_evidence": not any(
                error["error"] == "decision_missing_evidence" for error in integrity_errors
            ),
            "all_evidence_indices_valid": not any(
                error["error"] in {"range", "evidence_index"} for error in integrity_errors
            ),
            "neutral_decisions_have_no_evidence": not any(
                error["error"] == "not_mentioned_has_evidence" for error in integrity_errors
            ),
        },
    }


def analyze_cuad(path: Path) -> dict[str, Any]:
    question_count = 0
    answered_questions = 0
    answer_spans = 0
    question_categories: Counter[str] = Counter()
    integrity_errors: list[dict[str, Any]] = []

    with ZipFile(path) as archive:
        data = json.loads(archive.read("CUADv1.json"))
        documents = data["data"]
        for document in documents:
            for paragraph in document["paragraphs"]:
                context = paragraph["context"]
                for question in paragraph["qas"]:
                    question_count += 1
                    category = question["question"].split('"', 2)[1]
                    question_categories[category] += 1
                    answers = question.get("answers", [])
                    answered_questions += bool(answers)
                    answer_spans += len(answers)
                    for answer in answers:
                        start = answer["answer_start"]
                        text = answer["text"]
                        if context[start : start + len(text)] != text:
                            integrity_errors.append(
                                {
                                    "document": document["title"],
                                    "question_id": question["id"],
                                    "error": "answer_offset",
                                }
                            )

    required_categories = {
        "Document Name",
        "Parties",
        "Agreement Date",
        "Effective Date",
        "Expiration Date",
        "Renewal Term",
    }
    return {
        "source_url": CUAD_URL,
        "license": "CC BY 4.0",
        "sha256": _sha256_file(path),
        "version": data["version"],
        "documents": len(documents),
        "question_categories": len(question_categories),
        "questions": question_count,
        "answered_questions": answered_questions,
        "unanswered_questions": question_count - answered_questions,
        "answer_spans": answer_spans,
        "temporal_and_identity_categories_present": sorted(required_categories & set(question_categories)),
        "integrity_error_count": len(integrity_errors),
        "checks": {
            "all_answer_offsets_round_trip": not integrity_errors,
            "has_expected_41_categories": len(question_categories) == 41,
            "has_contract_identity_and_time_labels": required_categories <= set(question_categories),
        },
    }


def analyze_usaspending() -> dict[str, Any]:
    base = "https://api.usaspending.gov"
    award_url = f"{base}/api/v2/awards/{USASPENDING_AWARD_ID}/"
    count_url = f"{base}/api/v2/awards/count/transaction/{USASPENDING_AWARD_ID}/"
    transactions_url = f"{base}/api/v2/transactions/"
    award = _request_json(award_url)
    count = _request_json(count_url)
    transactions_response = _request_json(
        transactions_url,
        payload={"award_id": USASPENDING_AWARD_ID, "page": 1, "limit": 100},
    )
    transactions = transactions_response["results"]
    obligations = [float(item["federal_action_obligation"] or 0) for item in transactions]
    transaction_dates = [item["action_date"] for item in transactions]
    contract_data = award["latest_transaction_contract_data"]

    return {
        "source_urls": [award_url, count_url, transactions_url],
        "authority": "United States government award and transaction records",
        "award_id": USASPENDING_AWARD_ID,
        "award": {
            "piid": award["piid"],
            "description": award["description"],
            "total_obligation": award["total_obligation"],
            "recipient_name": award["recipient"]["recipient_name"],
            "recipient_uei": award["recipient"]["recipient_uei"],
            "awarding_agency": award["awarding_agency"]["toptier_agency"]["name"],
            "product_or_service_code": contract_data["product_or_service_code"],
            "product_or_service_description": contract_data["product_or_service_description"],
            "naics": contract_data["naics"],
            "period_of_performance": award["period_of_performance"],
        },
        "reported_transaction_count": count["transactions"],
        "transactions": [
            {
                "id": item["id"],
                "modification_number": item["modification_number"],
                "action_date": item["action_date"],
                "action_type": item["action_type_description"],
                "description": item["description"],
                "federal_action_obligation": item["federal_action_obligation"],
            }
            for item in sorted(transactions, key=lambda item: int(item["modification_number"]))
        ],
        "checks": {
            "transaction_count_matches": count["transactions"] == len(transactions),
            "transaction_ids_unique": len({item["id"] for item in transactions}) == len(transactions),
            "transaction_obligations_reconcile_to_award": math.isclose(
                sum(obligations), float(award["total_obligation"]), abs_tol=0.005
            ),
            "modification_history_present": any(
                item["modification_number"] not in {None, "0"} for item in transactions
            ),
            "latest_action_matches_last_modified_date": max(transaction_dates)
            == award["period_of_performance"]["last_modified_date"],
            "stable_recipient_identifier_present": bool(award["recipient"]["recipient_uei"]),
            "product_classification_present": bool(
                contract_data["product_or_service_code"] and contract_data["naics"]
            ),
        },
    }


TED_FIELDS = [
    "publication-number",
    "notice-identifier",
    "publication-date",
    "buyer-name",
    "buyer-identifier",
    "winner-name",
    "winner-identifier",
    "title-proc",
    "classification-cpv",
    "contract-conclusion-date",
    "change-notice-version-identifier",
    "modification-previous-notice-identifier",
]


def _ted_notice(notice_id: str) -> dict[str, Any]:
    response = _request_json(
        "https://api.ted.europa.eu/v3/notices/search",
        payload={
            "query": f'notice-identifier = "{notice_id}"',
            "fields": TED_FIELDS,
            "page": 1,
            "limit": 5,
            "scope": "ALL",
            "onlyLatestVersions": False,
        },
    )
    notices = response["notices"]
    if len(notices) != 1:
        raise ValidationError(f"expected one TED notice for {notice_id}, found {len(notices)}")
    return notices[0]


def _language_values(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    result: set[str] = set()
    for item in value.values():
        if isinstance(item, list):
            result.update(str(entry) for entry in item)
        else:
            result.add(str(item))
    return result


def analyze_ted() -> dict[str, Any]:
    current = _ted_notice(TED_CURRENT_NOTICE_ID)
    previous = _ted_notice(TED_PREVIOUS_NOTICE_ID)
    previous_refs = current.get("modification-previous-notice-identifier", [])
    normalized_previous_refs = {reference.rsplit("-", 1)[0] for reference in previous_refs}
    current_titles = _language_values(current.get("title-proc"))
    previous_titles = _language_values(previous.get("title-proc"))
    current_cpv = set(current.get("classification-cpv", []))
    previous_cpv = set(previous.get("classification-cpv", []))

    def compact(notice: dict[str, Any]) -> dict[str, Any]:
        return {key: notice.get(key) for key in TED_FIELDS if key in notice}

    return {
        "source_url": "https://api.ted.europa.eu/v3/notices/search",
        "authority": "Tenders Electronic Daily, Publications Office of the European Union",
        "current_notice": compact(current),
        "previous_notice": compact(previous),
        "checks": {
            "modification_link_resolves": TED_PREVIOUS_NOTICE_ID in normalized_previous_refs,
            "publication_order_is_temporal": previous["publication-date"] < current["publication-date"],
            "buyer_identifier_is_stable": bool(
                set(previous.get("buyer-identifier", []))
                & set(current.get("buyer-identifier", []))
            ),
            "procedure_title_is_stable": bool(current_titles & previous_titles),
            "product_classification_overlaps": bool(current_cpv & previous_cpv),
            "previous_notice_has_awarded_organizations": bool(previous.get("winner-identifier")),
        },
    }


def analyze_gleif() -> dict[str, Any]:
    url = f"https://api.gleif.org/api/v1/lei-records/{GLEIF_HP_LEI}"
    response = _request_json(url)
    attributes = response["data"]["attributes"]
    entity = attributes["entity"]
    previous_names = [
        item["name"]
        for item in entity.get("otherNames", [])
        if item.get("type") == "PREVIOUS_LEGAL_NAME"
    ]
    return {
        "source_url": url,
        "license": "CC0",
        "authority": "Global Legal Entity Identifier Foundation",
        "lei": attributes["lei"],
        "legal_name": entity["legalName"]["name"],
        "previous_legal_names": previous_names,
        "registry_authority_id": attributes["registration"]["validatedAt"]["id"],
        "registry_entity_id": attributes["registration"]["validatedAs"],
        "registration_status": attributes["registration"]["status"],
        "checks": {
            "lei_matches_requested_object": attributes["lei"] == GLEIF_HP_LEI,
            "current_legal_name_present": bool(entity["legalName"]["name"]),
            "previous_legal_name_present": "Hewlett-Packard Company" in previous_names,
            "registry_crosswalk_present": bool(
                attributes["registration"]["validatedAt"]["id"]
                and attributes["registration"]["validatedAs"]
            ),
        },
    }


def _flatten_checks(report: dict[str, Any]) -> list[tuple[str, bool]]:
    checks: list[tuple[str, bool]] = []
    for source_name, source in report["sources"].items():
        for check_name, passed in source["checks"].items():
            checks.append((f"{source_name}.{check_name}", bool(passed)))
    return checks


def build_report(cache_dir: Path) -> dict[str, Any]:
    contract_nli_path = _ensure_download(
        CONTRACT_NLI_URL,
        CONTRACT_NLI_SHA256,
        cache_dir / "contract-nli.zip",
    )
    cuad_path = _ensure_download(CUAD_URL, CUAD_SHA256, cache_dir / "cuad.zip")
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "public proxy data feasibility and integrity validation",
        "sources": {
            "contract_nli": analyze_contract_nli(contract_nli_path),
            "cuad": analyze_cuad(cuad_path),
            "usaspending": analyze_usaspending(),
            "ted": analyze_ted(),
            "gleif": analyze_gleif(),
        },
        "limitations": [
            "Public data can test technical mechanisms but cannot prove Knowledge has real user demand.",
            "All-public data cannot validate production Grant boundaries or unauthorized leakage.",
            "Dataset labels are external proxies, not the user's business gold set.",
            "This script validates source integrity and linked records; it does not compare retrieval experiment arms A-F.",
        ],
    }
    checks = _flatten_checks(report)
    report["summary"] = {
        "checks_total": len(checks),
        "checks_passed": sum(passed for _, passed in checks),
        "checks_failed": [name for name, passed in checks if not passed],
        "verdict": "proxy_data_ready" if all(passed for _, passed in checks) else "proxy_data_failed",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "knowledge-public-validation",
        help="directory for the two pinned public dataset archives",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON output path; stdout is always printed",
    )
    args = parser.parse_args()

    try:
        report = build_report(args.cache_dir)
    except ValidationError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["summary"]["verdict"] == "proxy_data_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
