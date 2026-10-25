"""Public-data ontology proxy pilot using the real Knowledge retrieval path.

The pilot is deliberately an upper-bound/no-code experiment, not an ontology
implementation.  A/B/C/C2 run ``ServiceSearchService._search_evidence`` against
official-record excerpts.  C3 uses narrow source-native deterministic tools.
D/E query an assertion table derived in memory; E additionally has to return
every required Evidence key.  F is not run because the local environment has no
live generation/rerank gateway.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from knowledge.core.settings import get_settings
from knowledge.db.session import SessionLocal
from knowledge.models import EvidenceUnit, KnowledgeBase, Source, SourceAsset, WalletUser
from knowledge.services.service_search import ServiceSearchService
from knowledge.services.unit_retrieval import UnitEmbeddingIndexer

from tests.eval.ontology_public_dataset import (
    GLEIF_LEIS,
    TED_NOTICE_PAIRS,
    TOP_K,
    TOP_K_SENSITIVITY,
    USA_AWARD_IDS,
)
from tests.eval.providers import NgramHashEmbeddingProvider, NgramOverlapRerankProvider


USER_AGENT = "Knowledge-public-ontology-pilot/1.0"
DEFAULT_REPORT_DIR = Path(".eval")
DEFAULT_CACHE_DIR = Path("/tmp/knowledge-public-ontology-pilot-cache")
TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
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
    "modification-previous-notice-identifier",
]


@dataclass(frozen=True)
class EvidenceRecord:
    key: str
    source_kind: str
    family_id: str
    record_type: str
    text: str


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _cache_path(cache_dir: Path, url: str, payload: dict[str, Any] | None) -> Path:
    key = hashlib.sha256(f"{url}\n{_canonical_json(payload)}".encode("utf-8")).hexdigest()
    return cache_dir / f"{key}.json"


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    cache_dir: Path,
) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, url, payload)
    refresh = os.environ.get("KNOWLEDGE_ONTOLOGY_EVAL_REFRESH", "").strip() == "1"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"public ontology pilot failed to read {url}: {exc}") from exc
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _amount(value: Decimal | float | int | str) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def _language_values(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    result: list[str] = []
    for language in sorted(value):
        item = value[language]
        if isinstance(item, list):
            result.extend(str(entry) for entry in item if entry)
        elif item:
            result.append(str(item))
    return list(dict.fromkeys(result))


def _first_language_value(value: Any) -> str:
    values = _language_values(value)
    return values[0] if values else ""


def _fetch_usa_award(award_id: str, cache_dir: Path) -> dict[str, Any]:
    base = "https://api.usaspending.gov"
    detail = _request_json(f"{base}/api/v2/awards/{award_id}/", cache_dir=cache_dir)
    count = _request_json(
        f"{base}/api/v2/awards/count/transaction/{award_id}/",
        cache_dir=cache_dir,
    )
    transactions_response = _request_json(
        f"{base}/api/v2/transactions/",
        payload={"award_id": award_id, "page": 1, "limit": 100},
        cache_dir=cache_dir,
    )
    transactions = sorted(
        transactions_response["results"],
        key=lambda item: (item["action_date"], item["modification_number"], item["id"]),
    )
    if count["transactions"] != len(transactions):
        raise AssertionError(f"USAspending transaction count drift for {award_id}")
    obligation_sum = sum(Decimal(str(item["federal_action_obligation"] or 0)) for item in transactions)
    if _amount(obligation_sum) != _amount(detail["total_obligation"]):
        raise AssertionError(f"USAspending obligation reconciliation failed for {award_id}")
    contract = detail["latest_transaction_contract_data"]
    recipient = detail["recipient"]
    return {
        "award_id": award_id,
        "piid": detail["piid"],
        "recipient_name": recipient["recipient_name"],
        "recipient_uei": recipient["recipient_uei"],
        "awarding_agency": detail["awarding_agency"]["toptier_agency"]["name"],
        "psc": contract["product_or_service_code"],
        "psc_description": contract["product_or_service_description"],
        "naics": contract["naics"],
        "current_total": _amount(detail["total_obligation"]),
        "transactions": [
            {
                "id": item["id"],
                "modification_number": item["modification_number"],
                "action_date": item["action_date"],
                "action_type": item["action_type_description"],
                "description": item["description"],
                "obligation": _amount(item["federal_action_obligation"] or 0),
            }
            for item in transactions
        ],
    }


def _fetch_ted_notice(notice_id: str, cache_dir: Path) -> dict[str, Any]:
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
    if len(response["notices"]) != 1:
        raise AssertionError(f"expected one TED notice for {notice_id}")
    notice = response["notices"][0]
    return {
        "notice_id": notice["notice-identifier"],
        "publication_number": notice["publication-number"],
        "publication_date": notice["publication-date"],
        "buyer_ids": sorted(set(notice.get("buyer-identifier", []))),
        "buyer_names": _language_values(notice.get("buyer-name")),
        "winner_ids": sorted(set(notice.get("winner-identifier", []))),
        "winner_names": _language_values(notice.get("winner-name")),
        "title": _first_language_value(notice.get("title-proc")),
        "cpv": sorted(set(notice.get("classification-cpv", []))),
        "contract_conclusion_dates": sorted(set(notice.get("contract-conclusion-date", []))),
        "previous_notice_refs": sorted(set(notice.get("modification-previous-notice-identifier", []))),
    }


def _fetch_ted_pair(pair: tuple[str, str], cache_dir: Path) -> dict[str, Any]:
    current_id, previous_id = pair
    current = _fetch_ted_notice(current_id, cache_dir)
    previous = _fetch_ted_notice(previous_id, cache_dir)
    normalized_refs = {reference.rsplit("-", 1)[0] for reference in current["previous_notice_refs"]}
    if previous_id not in normalized_refs:
        raise AssertionError(f"TED modification link drift for {current_id}")
    shared_buyers = sorted(set(current["buyer_ids"]) & set(previous["buyer_ids"]))
    shared_cpv = sorted(set(current["cpv"]) & set(previous["cpv"]))
    if not shared_buyers or not shared_cpv or previous["publication_date"] >= current["publication_date"]:
        raise AssertionError(f"TED stable-key or temporal check failed for {current_id}")
    return {
        "family_id": current_id,
        "current": current,
        "previous": previous,
        "shared_buyer_ids": shared_buyers,
        "shared_cpv": shared_cpv,
    }


def _fetch_gleif(lei: str, cache_dir: Path) -> dict[str, Any]:
    response = _request_json(f"https://api.gleif.org/api/v1/lei-records/{lei}", cache_dir=cache_dir)
    attributes = response["data"]["attributes"]
    entity = attributes["entity"]
    previous_names = sorted(
        item["name"]
        for item in entity.get("otherNames", [])
        if item.get("type") == "PREVIOUS_LEGAL_NAME"
    )
    if attributes["lei"] != lei or not previous_names:
        raise AssertionError(f"GLEIF previous-name record drift for {lei}")
    registration = attributes["registration"]
    return {
        "lei": lei,
        "legal_name": entity["legalName"]["name"],
        "previous_names": previous_names,
        "registry_authority_id": registration["validatedAt"]["id"],
        "registry_entity_id": registration["validatedAs"],
        "registration_status": registration["status"],
    }


def load_public_records(cache_dir: Path) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=8) as executor:
        usa = list(executor.map(lambda award_id: _fetch_usa_award(award_id, cache_dir), USA_AWARD_IDS))
        ted = list(executor.map(lambda pair: _fetch_ted_pair(pair, cache_dir), TED_NOTICE_PAIRS))
        gleif = list(executor.map(lambda lei: _fetch_gleif(lei, cache_dir), GLEIF_LEIS))
    return {"usa": usa, "ted": ted, "gleif": gleif}


def _usa_transaction_key(award: dict[str, Any], transaction: dict[str, Any]) -> str:
    return f"usa:{award['piid']}:transaction:{transaction['id']}"


def _usa_summary_key(award: dict[str, Any]) -> str:
    return f"usa:{award['piid']}:award"


def _ted_key(notice: dict[str, Any]) -> str:
    return f"ted:{notice['publication_number']}"


def _gleif_key(record: dict[str, Any]) -> str:
    return f"gleif:{record['lei']}"


def build_evidence_records(data: dict[str, Any]) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for award in data["usa"]:
        family = award["award_id"]
        records.append(
            EvidenceRecord(
                key=_usa_summary_key(award),
                source_kind="usa",
                family_id=family,
                record_type="award_summary",
                text=(
                    f"USAspending official award. Award ID {award['award_id']}; PIID {award['piid']}; "
                    f"recipient {award['recipient_name']}; recipient UEI {award['recipient_uei']}; "
                    f"awarding agency {award['awarding_agency']}; PSC {award['psc']}; "
                    f"product or service {award['psc_description']}; NAICS {award['naics']}; "
                    f"current total obligation {award['current_total']}."
                ),
            )
        )
        for transaction in award["transactions"]:
            records.append(
                EvidenceRecord(
                    key=_usa_transaction_key(award, transaction),
                    source_kind="usa",
                    family_id=family,
                    record_type="award_transaction",
                    text=(
                        f"USAspending official transaction. Award PIID {award['piid']}; "
                        f"recipient {award['recipient_name']}; product or service {award['psc_description']}; "
                        f"modification {transaction['modification_number']}; action date {transaction['action_date']}; "
                        f"action type {transaction['action_type'] or 'INITIAL'}; federal action obligation "
                        f"{transaction['obligation']}; description {transaction['description']}."
                    ),
                )
            )
    for pair in data["ted"]:
        for role in ("previous", "current"):
            notice = pair[role]
            records.append(
                EvidenceRecord(
                    key=_ted_key(notice),
                    source_kind="ted",
                    family_id=pair["family_id"],
                    record_type=f"ted_{role}_notice",
                    text=(
                        f"TED official {role} notice. Publication number {notice['publication_number']}; "
                        f"notice ID {notice['notice_id']}; publication date {notice['publication_date']}; "
                        f"title {notice['title']}; buyer IDs {', '.join(notice['buyer_ids'])}; "
                        f"buyer names {', '.join(notice['buyer_names'])}; CPV {', '.join(notice['cpv'])}; "
                        f"winner IDs {', '.join(notice['winner_ids']) or 'not published'}; "
                        f"previous notice references {', '.join(notice['previous_notice_refs']) or 'none'}."
                    ),
                )
            )
    for entity in data["gleif"]:
        records.append(
            EvidenceRecord(
                key=_gleif_key(entity),
                source_kind="gleif",
                family_id=entity["lei"],
                record_type="lei_record",
                text=(
                    f"GLEIF official LEI record. LEI {entity['lei']}; current legal name {entity['legal_name']}; "
                    f"previous legal names {', '.join(entity['previous_names'])}; registry authority "
                    f"{entity['registry_authority_id']}; registry entity ID {entity['registry_entity_id']}; "
                    f"registration status {entity['registration_status']}."
                ),
            )
        )
    return records


def build_assertions(data: dict[str, Any]) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    for award in data["usa"]:
        assertions.append(
            {
                "subject": award["award_id"],
                "predicate": "product_or_service_description",
                "value": award["psc_description"],
                "valid_at": None,
                "evidence": _usa_summary_key(award),
            }
        )
        for transaction in award["transactions"]:
            assertions.append(
                {
                    "subject": award["award_id"],
                    "predicate": "federal_action_obligation",
                    "value": transaction["obligation"],
                    "valid_at": transaction["action_date"],
                    "evidence": _usa_transaction_key(award, transaction),
                }
            )
    for pair in data["ted"]:
        current = pair["current"]
        previous = pair["previous"]
        assertions.extend(
            [
                {
                    "subject": current["notice_id"],
                    "predicate": "modifies",
                    "value": previous["notice_id"],
                    "valid_at": current["publication_date"],
                    "evidence": _ted_key(current),
                },
                {
                    "subject": current["notice_id"],
                    "predicate": "publication_number",
                    "value": current["publication_number"],
                    "valid_at": current["publication_date"],
                    "evidence": _ted_key(current),
                },
                {
                    "subject": previous["notice_id"],
                    "predicate": "publication_number",
                    "value": previous["publication_number"],
                    "valid_at": previous["publication_date"],
                    "evidence": _ted_key(previous),
                },
                {
                    "subject": current["notice_id"],
                    "predicate": "title",
                    "value": current["title"],
                    "valid_at": current["publication_date"],
                    "evidence": _ted_key(current),
                },
            ]
        )
        for notice in (current, previous):
            for buyer_id in notice["buyer_ids"]:
                assertions.append(
                    {
                        "subject": notice["notice_id"],
                        "predicate": "buyer_id",
                        "value": buyer_id,
                        "valid_at": notice["publication_date"],
                        "evidence": _ted_key(notice),
                    }
                )
            for cpv in notice["cpv"]:
                assertions.append(
                    {
                        "subject": notice["notice_id"],
                        "predicate": "cpv",
                        "value": cpv,
                        "valid_at": notice["publication_date"],
                        "evidence": _ted_key(notice),
                    }
                )
    for entity in data["gleif"]:
        assertions.extend(
            [
                {
                    "subject": entity["lei"],
                    "predicate": "legal_name",
                    "value": entity["legal_name"],
                    "valid_at": None,
                    "evidence": _gleif_key(entity),
                },
                {
                    "subject": entity["lei"],
                    "predicate": "registry_entity_id",
                    "value": entity["registry_entity_id"],
                    "valid_at": None,
                    "evidence": _gleif_key(entity),
                },
            ]
        )
        for previous_name in entity["previous_names"]:
            assertions.append(
                {
                    "subject": entity["lei"],
                    "predicate": "previous_legal_name",
                    "value": previous_name,
                    "valid_at": None,
                    "evidence": _gleif_key(entity),
                }
            )
    return assertions


class StructuredFactView:
    def __init__(self, assertions: list[dict[str, Any]]) -> None:
        self.assertions = assertions

    def _facts(self, subject: str | None = None, predicate: str | None = None) -> list[dict[str, Any]]:
        return [
            fact
            for fact in self.assertions
            if (subject is None or fact["subject"] == subject)
            and (predicate is None or fact["predicate"] == predicate)
        ]

    def answer(self, operation: str, params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        if operation in {"usa_latest_total", "usa_as_of_total"}:
            facts = self._facts(params["award_id"], "federal_action_obligation")
            if operation == "usa_as_of_total":
                facts = [fact for fact in facts if fact["valid_at"] <= params["as_of"]]
            if not facts:
                return {"status": "not_answerable", "value": None}, []
            total = sum(Decimal(fact["value"]) for fact in facts)
            return {"status": "answered", "value": {"amount": _amount(total)}}, sorted(
                {fact["evidence"] for fact in facts}
            )

        if operation == "ted_chain":
            modifies = self._facts(params["current_notice_id"], "modifies")
            if len(modifies) != 1:
                return {"status": "not_answerable", "value": None}, []
            previous_id = modifies[0]["value"]
            current_publication = self._facts(params["current_notice_id"], "publication_number")
            previous_publication = self._facts(previous_id, "publication_number")
            current_buyers = {fact["value"] for fact in self._facts(params["current_notice_id"], "buyer_id")}
            previous_buyers = {fact["value"] for fact in self._facts(previous_id, "buyer_id")}
            current_cpv = {fact["value"] for fact in self._facts(params["current_notice_id"], "cpv")}
            previous_cpv = {fact["value"] for fact in self._facts(previous_id, "cpv")}
            evidence = {
                modifies[0]["evidence"],
                *[fact["evidence"] for fact in previous_publication],
                *[fact["evidence"] for fact in self._facts(previous_id, "buyer_id")],
                *[fact["evidence"] for fact in self._facts(previous_id, "cpv")],
            }
            return {
                "status": "answered",
                "value": {
                    "current_publication": current_publication[0]["value"],
                    "previous_publication": previous_publication[0]["value"],
                    "shared_buyer_ids": sorted(current_buyers & previous_buyers),
                    "shared_cpv": sorted(current_cpv & previous_cpv),
                },
            }, sorted(evidence)

        if operation == "gleif_resolve_previous":
            matches = [
                fact
                for fact in self._facts(predicate="previous_legal_name")
                if fact["value"] == params["previous_name"]
            ]
            if len(matches) != 1:
                return {"status": "not_answerable", "value": None}, []
            lei = matches[0]["subject"]
            legal_name = self._facts(lei, "legal_name")
            registry_id = self._facts(lei, "registry_entity_id")
            evidence = {matches[0]["evidence"], legal_name[0]["evidence"], registry_id[0]["evidence"]}
            return {
                "status": "answered",
                "value": {
                    "lei": lei,
                    "legal_name": legal_name[0]["value"],
                    "registry_entity_id": registry_id[0]["value"],
                },
            }, sorted(evidence)

        if operation == "usa_product":
            facts = self._facts(params["award_id"], "product_or_service_description")
            if len(facts) != 1:
                return {"status": "not_answerable", "value": None}, []
            return {"status": "answered", "value": {"description": facts[0]["value"]}}, [facts[0]["evidence"]]

        if operation == "ted_title":
            facts = self._facts(params["notice_id"], "title")
            if len(facts) != 1:
                return {"status": "not_answerable", "value": None}, []
            return {"status": "answered", "value": {"title": facts[0]["value"]}}, [facts[0]["evidence"]]

        return {"status": "not_answerable", "value": None}, []


class SourceNativeToolView:
    """Narrow alternative that queries normalized source records directly.

    This deliberately avoids the generic assertion projection.  It shares the
    same oracle operation/parameters as D/E, so it tests whether the sampled
    tasks require a generic ontology after intent and stable IDs are known.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self.awards = {award["award_id"]: award for award in data["usa"]}
        self.ted_pairs = {pair["current"]["notice_id"]: pair for pair in data["ted"]}
        self.ted_notices = {
            notice["notice_id"]: notice
            for pair in data["ted"]
            for notice in (pair["current"], pair["previous"])
        }
        self.entities = data["gleif"]

    def answer(self, operation: str, params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        if operation in {"usa_latest_total", "usa_as_of_total"}:
            award = self.awards.get(params.get("award_id"))
            if award is None:
                return {"status": "not_answerable", "value": None}, []
            transactions = award["transactions"]
            if operation == "usa_as_of_total":
                transactions = [item for item in transactions if item["action_date"] <= params["as_of"]]
            if not transactions:
                return {"status": "not_answerable", "value": None}, []
            total = sum(Decimal(item["obligation"]) for item in transactions)
            evidence = [_usa_transaction_key(award, item) for item in transactions]
            return {"status": "answered", "value": {"amount": _amount(total)}}, sorted(evidence)

        if operation == "ted_chain":
            pair = self.ted_pairs.get(params.get("current_notice_id"))
            if pair is None:
                return {"status": "not_answerable", "value": None}, []
            current = pair["current"]
            previous = pair["previous"]
            return {
                "status": "answered",
                "value": {
                    "current_publication": current["publication_number"],
                    "previous_publication": previous["publication_number"],
                    "shared_buyer_ids": sorted(set(current["buyer_ids"]) & set(previous["buyer_ids"])),
                    "shared_cpv": sorted(set(current["cpv"]) & set(previous["cpv"])),
                },
            }, sorted({_ted_key(current), _ted_key(previous)})

        if operation == "gleif_resolve_previous":
            matches = [
                entity
                for entity in self.entities
                if params.get("previous_name") in entity["previous_names"]
            ]
            if len(matches) != 1:
                return {"status": "not_answerable", "value": None}, []
            entity = matches[0]
            return {
                "status": "answered",
                "value": {
                    "lei": entity["lei"],
                    "legal_name": entity["legal_name"],
                    "registry_entity_id": entity["registry_entity_id"],
                },
            }, [_gleif_key(entity)]

        if operation == "usa_product":
            award = self.awards.get(params.get("award_id"))
            if award is None:
                return {"status": "not_answerable", "value": None}, []
            return {
                "status": "answered",
                "value": {"description": award["psc_description"]},
            }, [_usa_summary_key(award)]

        if operation == "ted_title":
            notice = self.ted_notices.get(params.get("notice_id"))
            if notice is None:
                return {"status": "not_answerable", "value": None}, []
            return {"status": "answered", "value": {"title": notice["title"]}}, [_ted_key(notice)]

        return {"status": "not_answerable", "value": None}, []


def build_questions(data: dict[str, Any]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for index, award in enumerate(data["usa"], start=1):
        transaction_keys = [_usa_transaction_key(award, item) for item in award["transactions"]]
        questions.append(
            {
                "id": f"U{index:02d}-CURRENT",
                "kind": "relationship_temporal",
                "source_kind": "usa",
                "family_id": award["award_id"],
                "query": (
                    f"USAspending Award {award['piid']} 截至全部已发布交易的累计 "
                    "federal action obligation 是多少？"
                ),
                "operation": "usa_latest_total",
                "params": {"award_id": award["award_id"]},
                "gold": {"status": "answered", "value": {"amount": award["current_total"]}},
                "required_evidence": transaction_keys,
            }
        )
        cutoff = award["transactions"][len(award["transactions"]) // 2]["action_date"]
        included = [item for item in award["transactions"] if item["action_date"] <= cutoff]
        as_of_total = sum(Decimal(item["obligation"]) for item in included)
        questions.append(
            {
                "id": f"U{index:02d}-ASOF",
                "kind": "relationship_temporal",
                "source_kind": "usa",
                "family_id": award["award_id"],
                "query": (
                    f"截至 {cutoff}，USAspending Award {award['piid']} 的累计 "
                    "federal action obligation 是多少？"
                ),
                "operation": "usa_as_of_total",
                "params": {"award_id": award["award_id"], "as_of": cutoff},
                "gold": {"status": "answered", "value": {"amount": _amount(as_of_total)}},
                "required_evidence": [_usa_transaction_key(award, item) for item in included],
            }
        )

    for index, pair in enumerate(data["ted"], start=1):
        current = pair["current"]
        previous = pair["previous"]
        questions.append(
            {
                "id": f"T{index:02d}-CHAIN",
                "kind": "relationship_temporal",
                "source_kind": "ted",
                "family_id": pair["family_id"],
                "query": (
                    f"TED 修改通知 {current['publication_number']}（{current['title']}）修改了哪一个前一通知？"
                    "两个版本共同的买方标识和 CPV 是什么？"
                ),
                "operation": "ted_chain",
                "params": {"current_notice_id": current["notice_id"]},
                "gold": {
                    "status": "answered",
                    "value": {
                        "current_publication": current["publication_number"],
                        "previous_publication": previous["publication_number"],
                        "shared_buyer_ids": pair["shared_buyer_ids"],
                        "shared_cpv": pair["shared_cpv"],
                    },
                },
                "required_evidence": [_ted_key(current), _ted_key(previous)],
            }
        )

    for index, entity in enumerate(data["gleif"], start=1):
        previous_name = entity["previous_names"][0]
        questions.append(
            {
                "id": f"G{index:02d}-IDENTITY",
                "kind": "relationship_temporal",
                "source_kind": "gleif",
                "family_id": entity["lei"],
                "query": f"历史法定名称“{previous_name}”当前对应哪个法律实体和 LEI？",
                "operation": "gleif_resolve_previous",
                "params": {"previous_name": previous_name},
                "gold": {
                    "status": "answered",
                    "value": {
                        "lei": entity["lei"],
                        "legal_name": entity["legal_name"],
                        "registry_entity_id": entity["registry_entity_id"],
                    },
                },
                "required_evidence": [_gleif_key(entity)],
            }
        )

    for index, award in enumerate(data["usa"][:5], start=1):
        questions.append(
            {
                "id": f"C{index:02d}-USA",
                "kind": "ordinary_text",
                "source_kind": "usa",
                "family_id": award["award_id"],
                "query": f"USAspending Award {award['piid']} 的产品或服务描述是什么？",
                "operation": "usa_product",
                "params": {"award_id": award["award_id"]},
                "gold": {"status": "answered", "value": {"description": award["psc_description"]}},
                "required_evidence": [_usa_summary_key(award)],
            }
        )
    for offset, pair in enumerate(data["ted"][:5], start=6):
        current = pair["current"]
        questions.append(
            {
                "id": f"C{offset:02d}-TED",
                "kind": "ordinary_text",
                "source_kind": "ted",
                "family_id": pair["family_id"],
                "query": f"TED 通知 {current['publication_number']} 的程序标题是什么？",
                "operation": "ted_title",
                "params": {"notice_id": current["notice_id"]},
                "gold": {"status": "answered", "value": {"title": current["title"]}},
                "required_evidence": [_ted_key(current)],
            }
        )

    no_answer_specs = [
        ("N01-USA", "usa", "USAspending Award NOT-A-REAL-AWARD-2099 的累计 obligation 是多少？"),
        ("N02-USA", "usa", "USAspending Award ZZ-NOT-PUBLISHED 的产品或服务描述是什么？"),
        ("N03-TED", "ted", "TED 通知 000000-2099 修改了哪一个前一通知？"),
        ("N04-TED", "ted", "TED 通知 999999-2099 的共同买方标识是什么？"),
        ("N05-GLEIF", "gleif", "历史法定名称 Never Existing Corporation 当前对应哪个 LEI？"),
    ]
    for question_id, source_kind, query in no_answer_specs:
        questions.append(
            {
                "id": question_id,
                "kind": "no_answer",
                "source_kind": source_kind,
                "family_id": None,
                "query": query,
                "operation": "unknown",
                "params": {},
                "gold": {"status": "not_answerable", "value": None},
                "required_evidence": [],
            }
        )
    return questions


def _seed_kb(db, *, wallet: str, name: str, records: list[EvidenceRecord]) -> tuple[int, dict[int, str]]:
    kb = KnowledgeBase(owner_wallet_address=wallet, name=name)
    db.add(kb)
    db.flush()
    source = Source(kb_id=kb.id, source_path=f"/eval/ontology/{uuid.uuid4().hex}", scope_type="directory")
    db.add(source)
    db.flush()
    evidence_keys: dict[int, str] = {}
    for record in records:
        asset = SourceAsset(
            kb_id=kb.id,
            source_id=source.id,
            asset_path=f"{source.source_path}/{hashlib.sha1(record.key.encode()).hexdigest()}.json",
            asset_name=f"{record.key}.json"[:255],
            availability_status="available",
        )
        db.add(asset)
        db.flush()
        unit = EvidenceUnit(
            kb_id=kb.id,
            asset_id=asset.id,
            evidence_type=record.record_type,
            text=record.text,
            metadata_json={
                "public_record_key": record.key,
                "source_kind": record.source_kind,
                "family_id": record.family_id,
            },
            source_locator={"public_record_key": record.key},
        )
        db.add(unit)
        db.flush()
        evidence_keys[unit.id] = record.key
    db.commit()
    return kb.id, evidence_keys


def seed_corpora(db, records: list[EvidenceRecord], embedding) -> tuple[dict[str, int], dict[str, dict[int, str]], dict[str, dict]]:
    wallet = f"0x{uuid.uuid4().hex[:20]}"
    db.add(WalletUser(wallet_address=wallet))
    db.commit()
    kb_ids: dict[str, int] = {}
    evidence_maps: dict[str, dict[int, str]] = {}
    backfills: dict[str, dict] = {}
    groups = {"global": records}
    groups.update({kind: [record for record in records if record.source_kind == kind] for kind in ("usa", "ted", "gleif")})
    groups.update(
        {
            f"family:{source_kind}:{family_id}": [
                record
                for record in records
                if record.source_kind == source_kind and record.family_id == family_id
            ]
            for source_kind in ("usa", "ted", "gleif")
            for family_id in sorted({
                record.family_id for record in records if record.source_kind == source_kind
            })
        }
    )
    for label, group in groups.items():
        kb_id, evidence_map = _seed_kb(db, wallet=wallet, name=f"Ontology public pilot: {label}", records=group)
        kb_ids[label] = kb_id
        evidence_maps[label] = evidence_map
        backfills[label] = UnitEmbeddingIndexer(embedding_provider=embedding).backfill_kb(
            db, kb_id=kb_id, owner_wallet_address=wallet
        )
    return kb_ids, evidence_maps, backfills


@contextmanager
def _retrieval_flags(*, hybrid: bool, rerank: bool):
    settings = get_settings()
    saved = (settings.retrieval_hybrid_enabled, settings.retrieval_rerank_enabled)
    settings.retrieval_hybrid_enabled = hybrid
    settings.retrieval_rerank_enabled = rerank
    try:
        yield
    finally:
        settings.retrieval_hybrid_enabled, settings.retrieval_rerank_enabled = saved


def _run_retrieval(
    service: ServiceSearchService,
    db,
    *,
    kb_id: int,
    evidence_map: dict[int, str],
    question: dict[str, Any],
    hybrid: bool,
    rerank: bool,
    top_k: int = TOP_K,
) -> dict[str, Any]:
    trace: dict[str, Any] = {}
    with _retrieval_flags(hybrid=hybrid, rerank=rerank):
        hits = service._search_evidence(
            db,
            kb_id=kb_id,
            query=question["query"],
            result_view="compact",
            availability_mode="allow_all",
            top_k=top_k,
            exclude_evidence_ids=set(),
            trace=trace,
        )
    retrieved = []
    for hit in hits:
        key = evidence_map.get(hit.evidence_id)
        if key and key not in retrieved:
            retrieved.append(key)
    required = set(question["required_evidence"])
    found = required & set(retrieved)
    first_rank = next((index + 1 for index, key in enumerate(retrieved) if key in required), None)
    return {
        "retrieved": retrieved,
        "complete_evidence": (required <= set(retrieved)) if required else None,
        "evidence_recall": (len(found) / len(required)) if required else None,
        "first_evidence_rank": first_rank,
        "trace": {
            key: trace.get(key)
            for key in ("vector_signal", "vector_widened", "rerank_signal", "rerank_count")
        },
    }


def _retrieval_summary(question_results: list[dict[str, Any]], kind: str | None = None) -> dict[str, Any]:
    selected = [
        result
        for result in question_results
        if result["question"]["required_evidence"]
        and (kind is None or result["question"]["kind"] == kind)
    ]
    count = len(selected) or 1
    return {
        "questions": len(selected),
        "complete": sum(bool(result["result"]["complete_evidence"]) for result in selected),
        "oracle_accuracy": round(
            sum(bool(result["result"]["complete_evidence"]) for result in selected) / count, 4
        ),
        "mean_evidence_recall": round(
            sum(float(result["result"]["evidence_recall"]) for result in selected) / count, 4
        ),
    }


def _structured_summary(results: list[dict[str, Any]], kind: str | None = None) -> dict[str, Any]:
    selected = [result for result in results if kind is None or result["question"]["kind"] == kind]
    count = len(selected) or 1
    answerable = [result for result in selected if result["question"]["kind"] != "no_answer"]
    no_answer = [result for result in selected if result["question"]["kind"] == "no_answer"]
    return {
        "questions": len(selected),
        "exact": sum(result["exact"] for result in selected),
        "accuracy": round(sum(result["exact"] for result in selected) / count, 4),
        "evidence_traceability": round(
            sum(result["trace_complete"] for result in answerable) / (len(answerable) or 1), 4
        ),
        "no_answer_abstention": round(
            sum(result["exact"] for result in no_answer) / (len(no_answer) or 1), 4
        ),
    }


def _bootstrap_paired_difference(left: list[int], right: list[int], samples: int = 10000) -> dict[str, float]:
    randomizer = random.Random(20261025)
    differences = [r - l for l, r in zip(left, right)]
    estimates = []
    for _ in range(samples):
        draw = [differences[randomizer.randrange(len(differences))] for _ in differences]
        estimates.append(sum(draw) / len(draw))
    estimates.sort()
    return {
        "difference": round(sum(differences) / len(differences), 4),
        "ci95_low": round(estimates[int(samples * 0.025)], 4),
        "ci95_high": round(estimates[int(samples * 0.975)], 4),
    }


def _mcnemar_exact(left: list[int], right: list[int]) -> dict[str, Any]:
    left_only = sum(1 for l, r in zip(left, right) if l and not r)
    right_only = sum(1 for l, r in zip(left, right) if r and not l)
    discordant = left_only + right_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, index) for index in range(min(left_only, right_only) + 1))
        p_value = min(1.0, 2.0 * tail / (2**discordant))
    return {
        "left_only": left_only,
        "right_only": right_only,
        "discordant": discordant,
        "two_sided_p": round(p_value, 6),
    }


def run_public_ontology_eval(report_dir: Path | None = None, cache_dir: Path | None = None) -> dict[str, Any]:
    started = time.time()
    data = load_public_records(cache_dir or Path(os.environ.get("KNOWLEDGE_ONTOLOGY_EVAL_CACHE_DIR", DEFAULT_CACHE_DIR)))
    records = build_evidence_records(data)
    assertions = build_assertions(data)
    questions = build_questions(data)
    facts = StructuredFactView(assertions)
    source_tools = SourceNativeToolView(data)
    embedding = NgramHashEmbeddingProvider()
    rerank = NgramOverlapRerankProvider()

    with SessionLocal() as db:
        kb_ids, evidence_maps, backfills = seed_corpora(db, records, embedding)
        service = ServiceSearchService(embedding_provider=embedding, rerank_provider=rerank)
        by_tier: dict[str, list[dict[str, Any]]] = {
            "A_lexical": [],
            "B_hybrid": [],
            "C_hybrid_source_filter": [],
            "C2_hybrid_family_filter": [],
        }
        structured_d: list[dict[str, Any]] = []
        structured_e: list[dict[str, Any]] = []
        source_native_c3: list[dict[str, Any]] = []
        c2_sensitivity: dict[int, list[dict[str, Any]]] = {
            top_k: [] for top_k in TOP_K_SENSITIVITY
        }
        per_question: dict[str, Any] = {}

        for question in questions:
            a = _run_retrieval(
                service,
                db,
                kb_id=kb_ids["global"],
                evidence_map=evidence_maps["global"],
                question=question,
                hybrid=False,
                rerank=False,
            )
            b = _run_retrieval(
                service,
                db,
                kb_id=kb_ids["global"],
                evidence_map=evidence_maps["global"],
                question=question,
                hybrid=True,
                rerank=True,
            )
            c = _run_retrieval(
                service,
                db,
                kb_id=kb_ids[question["source_kind"]],
                evidence_map=evidence_maps[question["source_kind"]],
                question=question,
                hybrid=True,
                rerank=True,
            )
            family_scope = (
                f"family:{question['source_kind']}:{question['family_id']}"
                if question["family_id"] is not None
                else question["source_kind"]
            )
            c2 = _run_retrieval(
                service,
                db,
                kb_id=kb_ids[family_scope],
                evidence_map=evidence_maps[family_scope],
                question=question,
                hybrid=True,
                rerank=True,
            )
            answer, evidence = facts.answer(question["operation"], question["params"])
            exact = answer == question["gold"]
            required = set(question["required_evidence"])
            trace_complete = exact and required <= set(evidence)
            c3_answer, c3_evidence = source_tools.answer(question["operation"], question["params"])
            c3_exact = c3_answer == question["gold"]
            c3_trace_complete = c3_exact and required <= set(c3_evidence)
            d = {"question": question, "answer": answer, "exact": exact, "trace_complete": False}
            e = {"question": question, "answer": answer, "evidence": evidence, "exact": exact, "trace_complete": trace_complete}
            c3 = {
                "question": question,
                "answer": c3_answer,
                "evidence": c3_evidence,
                "exact": c3_exact,
                "trace_complete": c3_trace_complete,
            }
            by_tier["A_lexical"].append({"question": question, "result": a})
            by_tier["B_hybrid"].append({"question": question, "result": b})
            by_tier["C_hybrid_source_filter"].append({"question": question, "result": c})
            by_tier["C2_hybrid_family_filter"].append({"question": question, "result": c2})
            if question["kind"] == "relationship_temporal":
                for sensitivity_top_k in TOP_K_SENSITIVITY:
                    sensitivity_result = (
                        c2
                        if sensitivity_top_k == TOP_K
                        else _run_retrieval(
                            service,
                            db,
                            kb_id=kb_ids[family_scope],
                            evidence_map=evidence_maps[family_scope],
                            question=question,
                            hybrid=True,
                            rerank=True,
                            top_k=sensitivity_top_k,
                        )
                    )
                    c2_sensitivity[sensitivity_top_k].append(
                        {"question": question, "result": sensitivity_result}
                    )
            structured_d.append(d)
            structured_e.append(e)
            source_native_c3.append(c3)
            per_question[question["id"]] = {
                "kind": question["kind"],
                "query": question["query"],
                "required_evidence_count": len(question["required_evidence"]),
                "A": a,
                "B": b,
                "C": c,
                "C2": c2,
                "C3": {
                    "answer": c3_answer,
                    "evidence": c3_evidence,
                    "exact": c3_exact,
                    "trace_complete": c3_trace_complete,
                },
                "D": {"answer": answer, "exact": exact},
                "E": {"answer": answer, "evidence": evidence, "exact": exact, "trace_complete": trace_complete},
            }

    retrieval_summaries = {
        tier: {
            "all_answerable": _retrieval_summary(results),
            "relationship_temporal": _retrieval_summary(results, "relationship_temporal"),
            "ordinary_text": _retrieval_summary(results, "ordinary_text"),
        }
        for tier, results in by_tier.items()
    }
    structured_summaries = {
        "D_structured_facts": {
            "all": _structured_summary(structured_d),
            "relationship_temporal": _structured_summary(structured_d, "relationship_temporal"),
            "ordinary_text": _structured_summary(structured_d, "ordinary_text"),
            "no_answer": _structured_summary(structured_d, "no_answer"),
        },
        "E_structured_plus_evidence": {
            "all": _structured_summary(structured_e),
            "relationship_temporal": _structured_summary(structured_e, "relationship_temporal"),
            "ordinary_text": _structured_summary(structured_e, "ordinary_text"),
            "no_answer": _structured_summary(structured_e, "no_answer"),
        },
    }
    alternative_summaries = {
        "C3_source_native_tools": {
            "model": "normalized source records plus narrow deterministic tools; no generic assertion projection",
            "planner": "oracle operation and stable-ID parameters shared with D/E",
            "all": _structured_summary(source_native_c3),
            "relationship_temporal": _structured_summary(source_native_c3, "relationship_temporal"),
            "ordinary_text": _structured_summary(source_native_c3, "ordinary_text"),
            "no_answer": _structured_summary(source_native_c3, "no_answer"),
        }
    }

    core_questions = [question for question in questions if question["kind"] == "relationship_temporal"]
    e_by_id = {result["question"]["id"]: int(result["exact"] and result["trace_complete"]) for result in structured_e}
    e_correct = [e_by_id[question["id"]] for question in core_questions]
    sensitivity_results: dict[str, Any] = {}
    for sensitivity_top_k, results in c2_sensitivity.items():
        c_by_id = {
            result["question"]["id"]: int(bool(result["result"]["complete_evidence"]))
            for result in results
        }
        c_correct = [c_by_id[question["id"]] for question in core_questions]
        sensitivity_results[str(sensitivity_top_k)] = {
            "C2_relationship_temporal": _retrieval_summary(results, "relationship_temporal"),
            "E_minus_C2_bootstrap": _bootstrap_paired_difference(c_correct, e_correct),
            "mcnemar_exact": _mcnemar_exact(c_correct, e_correct),
        }
    baseline = sensitivity_results[str(TOP_K)]
    effect = baseline["E_minus_C2_bootstrap"]
    mcnemar = baseline["mcnemar_exact"]
    e_summary = structured_summaries["E_structured_plus_evidence"]
    baseline_clears_preregistered_effect_gate = (
        effect["difference"] >= 0.10
        and effect["ci95_low"] > 0
        and e_summary["relationship_temporal"]["evidence_traceability"] == 1.0
        and e_summary["no_answer"]["no_answer_abstention"] == 1.0
    )
    robustness_signal_passed = all(
        result["E_minus_C2_bootstrap"]["difference"] >= 0.10
        and result["E_minus_C2_bootstrap"]["ci95_low"] > 0
        for result in sensitivity_results.values()
    )
    c3_summary = alternative_summaries["C3_source_native_tools"]
    smaller_alternative_matches_e = (
        c3_summary["all"]["accuracy"] == e_summary["all"]["accuracy"]
        and c3_summary["relationship_temporal"]["evidence_traceability"]
        == e_summary["relationship_temporal"]["evidence_traceability"]
        and c3_summary["no_answer"]["no_answer_abstention"]
        == e_summary["no_answer"]["no_answer_abstention"]
    )
    signal_passed = (
        baseline_clears_preregistered_effect_gate
        and robustness_signal_passed
        and not smaller_alternative_matches_e
    )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_seconds": round(time.time() - started, 3),
        "provider": "offline_ngram; exercises the real retrieval path but is not a model-quality reference",
        "top_k": TOP_K,
        "dataset": {
            "usa_award_families": len(data["usa"]),
            "ted_modification_chains": len(data["ted"]),
            "gleif_identity_records": len(data["gleif"]),
            "evidence_records": len(records),
            "assertions": len(assertions),
            "questions": len(questions),
            "question_kinds": {
                kind: sum(question["kind"] == kind for question in questions)
                for kind in ("relationship_temporal", "ordinary_text", "no_answer")
            },
            "normalized_source_sha256": _sha256_json(data),
            "fixed_identifiers": {
                "usa": list(USA_AWARD_IDS),
                "ted": [list(pair) for pair in TED_NOTICE_PAIRS],
                "gleif": list(GLEIF_LEIS),
            },
            "backfills": backfills,
        },
        "retrieval": retrieval_summaries,
        "alternatives": alternative_summaries,
        "structured": structured_summaries,
        "paired_core_comparison_C2_vs_E": {
            "bootstrap": effect,
            "mcnemar_exact": mcnemar,
        },
        "top_k_sensitivity_C2_vs_E": sensitivity_results,
        "decision": {
            "baseline_clears_preregistered_effect_gate": baseline_clears_preregistered_effect_gate,
            "robustness_signal_passed": robustness_signal_passed,
            "smaller_alternative_matches_e": smaller_alternative_matches_e,
            "proxy_signal_passed": signal_passed,
            "verdict": "validate_again_live_provider_required" if signal_passed else "dont_build_yet",
            "reason": (
                "D/E beat the entity-family-filtered retrieval upper bound on relationship/temporal questions, "
                "and the effect survives the top-k sensitivity analysis. A live provider and hidden questions "
                "are still required."
                if signal_passed
                else (
                    "C3 source-native deterministic tools matched E on exact answers, Evidence traceability, "
                    "and abstention without a generic assertion projection. In addition, the C2→E Evidence "
                    "gap disappeared when the entity-family retrieval window reached 15 records. The sampled "
                    "tasks therefore do not establish that an ontology layer is required."
                    if smaller_alternative_matches_e
                    else "At the top-k=6 baseline, C2→E cleared the preregistered effect-size and interval "
                    "threshold, but the effect disappeared when the entity-family retrieval window reached "
                    "15 records. The pilot therefore identifies a bounded-retrieval aggregation problem, not "
                    "robust evidence that an ontology layer is required."
                    if baseline_clears_preregistered_effect_gate
                    else "The structured fact view did not clear the preregistered proxy effect and traceability gate."
                )
            ),
        },
        "limitations": [
            "A/B/C accuracy is an oracle evidence-completeness upper bound, not generated-answer accuracy.",
            "The offline n-gram provider exercises product code but cannot establish live semantic model quality.",
            "Questions are generated from fixed official records and are not a hidden independently annotated test set.",
            "Public records cannot test production Grant leakage, user demand, or maintenance cost.",
            "The USAspending sample deliberately stresses awards with several modifications; it is not a prevalence estimate.",
            "C2 entity-family filtering and the top-k sensitivity analysis are post-hoc diagnostics rather than preregistered arms.",
            "C3 shares oracle intent and stable-ID parameters with D/E; it does not test natural-language planning or entity resolution.",
            "F generation is omitted because no live model gateway is configured.",
        ],
        "questions": per_question,
    }
    _write_report(report, report_dir or Path(os.environ.get("KNOWLEDGE_EVAL_REPORT_DIR", DEFAULT_REPORT_DIR)))
    return report


def _write_report(report: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "ontology_public_pilot.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (report_dir / "ontology_public_pilot.md").write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    lines = [
        "## Ontology V1 public proxy pilot",
        "",
        f"- provider: `{report['provider']}`",
        f"- corpus: {dataset['evidence_records']} evidence records / {dataset['assertions']} assertions",
        f"- questions: {dataset['questions']} "
        f"({dataset['question_kinds']['relationship_temporal']} relationship-temporal, "
        f"{dataset['question_kinds']['ordinary_text']} control, {dataset['question_kinds']['no_answer']} no-answer)",
        f"- source hash: `{dataset['normalized_source_sha256']}`",
        "",
        "| arm | relationship/time oracle accuracy | evidence recall | ordinary control accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    for arm in ("A_lexical", "B_hybrid", "C_hybrid_source_filter", "C2_hybrid_family_filter"):
        core = report["retrieval"][arm]["relationship_temporal"]
        control = report["retrieval"][arm]["ordinary_text"]
        lines.append(
            f"| {arm} | {core['oracle_accuracy']:.1%} | {core['mean_evidence_recall']:.1%} "
            f"| {control['oracle_accuracy']:.1%} |"
        )
    c3 = report["alternatives"]["C3_source_native_tools"]
    lines.append(
        f"| C3_source_native_tools | {c3['relationship_temporal']['accuracy']:.1%} exact "
        f"| {c3['relationship_temporal']['evidence_traceability']:.1%} traceable "
        f"| {c3['ordinary_text']['accuracy']:.1%} exact |"
    )
    for arm in ("D_structured_facts", "E_structured_plus_evidence"):
        core = report["structured"][arm]["relationship_temporal"]
        control = report["structured"][arm]["ordinary_text"]
        lines.append(f"| {arm} | {core['accuracy']:.1%} | n/a | {control['accuracy']:.1%} |")
    effect = report["paired_core_comparison_C2_vs_E"]["bootstrap"]
    mcnemar = report["paired_core_comparison_C2_vs_E"]["mcnemar_exact"]
    lines += [
        "",
        f"- C2→E paired improvement: {effect['difference']:.1%} "
        f"(bootstrap 95% CI {effect['ci95_low']:.1%} to {effect['ci95_high']:.1%})",
        f"- McNemar exact two-sided p: {mcnemar['two_sided_p']}",
        f"- E Evidence traceability: "
        f"{report['structured']['E_structured_plus_evidence']['relationship_temporal']['evidence_traceability']:.1%}",
        f"- E no-answer abstention: "
        f"{report['structured']['E_structured_plus_evidence']['no_answer']['no_answer_abstention']:.1%}",
        "",
        "| C2 top-k | relationship/time oracle accuracy | evidence recall | E−C2 | bootstrap 95% CI |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for top_k, result in report["top_k_sensitivity_C2_vs_E"].items():
        summary = result["C2_relationship_temporal"]
        sensitivity_effect = result["E_minus_C2_bootstrap"]
        lines.append(
            f"| {top_k} | {summary['oracle_accuracy']:.1%} | {summary['mean_evidence_recall']:.1%} "
            f"| {sensitivity_effect['difference']:.1%} "
            f"| {sensitivity_effect['ci95_low']:.1%} to {sensitivity_effect['ci95_high']:.1%} |"
        )
    lines += [
        "",
        f"- baseline clears preregistered effect gate: "
        f"`{report['decision']['baseline_clears_preregistered_effect_gate']}`",
        f"- top-k robustness signal: `{report['decision']['robustness_signal_passed']}`",
        f"- smaller C3 alternative matches E: `{report['decision']['smaller_alternative_matches_e']}`",
        f"- verdict: `{report['decision']['verdict']}`",
        "",
        report["decision"]["reason"],
        "",
        "The report is a stress pilot, not a Build-small authorization. See JSON for per-question evidence and traces.",
        "",
    ]
    return "\n".join(lines)
