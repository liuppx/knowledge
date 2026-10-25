"""Deterministic natural-language planner for the narrow C3 source tools."""

from __future__ import annotations

import re
from typing import Any


_DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})(?:-|/|年)(?P<month>\d{1,2})(?:-|/|月)(?P<day>\d{1,2})(?:日)?"
)
_UUID_PATTERN = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_TED_PUBLICATION_PATTERN = re.compile(r"\b\d{5,6}-\d{4}\b")
_FULL_AWARD_PATTERN = re.compile(r"\bCONT_AWD_[A-Z0-9_]+\b", re.I)

_AMOUNT_HINTS = ("obligation", "金额", "义务", "承诺", "总额", "汇总", "累计", "合计")
_PRODUCT_HINTS = (
    "product or service",
    "产品或服务",
    "产品/服务",
    "服务/产品",
    "采购品类",
    "产品描述",
    "服务描述",
    "买的",
    "采购的服务",
    "采购的产品",
)
_TED_CHAIN_HINTS = (
    "previous notice",
    "上一份",
    "前一公告",
    "版本链",
    "修改链",
    "改的是",
    "追溯",
    "共同",
    "共有",
    "交集",
)
_TED_TITLE_HINTS = ("title-proc", "procurement title", "程序标题", "程序名称", "标题")
_TED_CHAIN_NEGATIONS = (
    "不需要版本链",
    "无需版本链",
    "不要版本链",
    "不查版本链",
    "without the version chain",
)
_GLEIF_RESOLUTION_HINTS = (
    "lei",
    "当前法律实体",
    "当前公司",
    "当前法律名称",
    "现在登记",
    "现在对应",
    "现在使用",
    "后来登记",
    "更名后",
    "解析到",
)


def _normalize(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(_normalize(hint) in text for hint in hints)


def _extract_date(text: str) -> str | None:
    match = _DATE_PATTERN.search(text)
    if not match:
        return None
    return f"{int(match['year']):04d}-{int(match['month']):02d}-{int(match['day']):02d}"


class DeterministicSourcePlanner:
    """Plan only when intent and a unique stable source identifier are explicit."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.awards_by_id = {award["award_id"].casefold(): award for award in data["usa"]}
        self.awards_by_piid = {award["piid"].casefold(): award for award in data["usa"]}
        self.awards_by_recipient: dict[str, list[dict[str, Any]]] = {}
        for award in data["usa"]:
            self.awards_by_recipient.setdefault(_normalize(award["recipient_name"]), []).append(award)

        self.ted_by_id: dict[str, dict[str, Any]] = {}
        self.ted_by_publication: dict[str, dict[str, Any]] = {}
        self.current_ted_ids: set[str] = set()
        for pair in data["ted"]:
            self.current_ted_ids.add(pair["current"]["notice_id"].casefold())
            for notice in (pair["current"], pair["previous"]):
                self.ted_by_id[notice["notice_id"].casefold()] = notice
                self.ted_by_publication[notice["publication_number"].casefold()] = notice

        self.previous_names = sorted(
            (
                (_normalize(previous_name), previous_name)
                for entity in data["gleif"]
                for previous_name in entity["previous_names"]
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    @staticmethod
    def _abstain(reason: str) -> dict[str, Any]:
        return {"status": "abstain", "operation": None, "params": None, "reason": reason}

    @staticmethod
    def _planned(operation: str, params: dict[str, Any], identifier_kind: str) -> dict[str, Any]:
        return {
            "status": "planned",
            "operation": operation,
            "params": params,
            "identifier_kind": identifier_kind,
        }

    def _resolve_award(self, query: str, normalized: str) -> tuple[dict[str, Any] | None, str]:
        full_id_candidates: dict[str, dict[str, Any]] = {}
        for match in _FULL_AWARD_PATTERN.findall(query):
            award = self.awards_by_id.get(match.casefold())
            if award:
                full_id_candidates[award["award_id"]] = award
        if len(full_id_candidates) == 1:
            return next(iter(full_id_candidates.values())), "award_id"
        if len(full_id_candidates) > 1:
            return None, "ambiguous_award_id"

        piid_candidates: dict[str, dict[str, Any]] = {}
        for piid, award in self.awards_by_piid.items():
            if re.search(rf"(?<![a-z0-9]){re.escape(piid)}(?![a-z0-9])", normalized):
                piid_candidates[award["award_id"]] = award
        if len(piid_candidates) == 1:
            return next(iter(piid_candidates.values())), "piid"
        if len(piid_candidates) > 1:
            return None, "ambiguous_piid"

        recipient_candidates: dict[str, dict[str, Any]] = {}
        for recipient, awards in self.awards_by_recipient.items():
            if recipient in normalized:
                for award in awards:
                    recipient_candidates[award["award_id"]] = award
        if len(recipient_candidates) != 1:
            return None, "ambiguous_or_unknown_award"
        return next(iter(recipient_candidates.values())), "recipient"

    def _resolve_ted(self, query: str) -> tuple[dict[str, Any] | None, str]:
        candidates: dict[str, tuple[dict[str, Any], str]] = {}
        for match in _UUID_PATTERN.findall(query):
            notice = self.ted_by_id.get(match.casefold())
            if notice:
                candidates[notice["notice_id"]] = (notice, "notice_id")
        for match in _TED_PUBLICATION_PATTERN.findall(query):
            notice = self.ted_by_publication.get(match.casefold())
            if notice:
                candidates[notice["notice_id"]] = (notice, "publication_number")
        if len(candidates) != 1:
            return None, "ambiguous_or_unknown_notice"
        return next(iter(candidates.values()))

    def plan(self, query: str) -> dict[str, Any]:
        normalized = _normalize(query)
        award, award_identifier_kind = self._resolve_award(query, normalized)
        if award is not None:
            if _contains_any(normalized, _PRODUCT_HINTS):
                return self._planned("usa_product", {"award_id": award["award_id"]}, award_identifier_kind)
            if _contains_any(normalized, _AMOUNT_HINTS):
                as_of = _extract_date(query)
                if as_of:
                    return self._planned(
                        "usa_as_of_total",
                        {"award_id": award["award_id"], "as_of": as_of},
                        award_identifier_kind,
                    )
                return self._planned(
                    "usa_latest_total", {"award_id": award["award_id"]}, award_identifier_kind
                )
            return self._abstain("unsupported_award_intent")

        notice, notice_identifier_kind = self._resolve_ted(query)
        if notice is not None:
            notice_id = notice["notice_id"]
            wants_title = _contains_any(normalized, _TED_TITLE_HINTS)
            chain_is_negated = _contains_any(normalized, _TED_CHAIN_NEGATIONS)
            if wants_title and chain_is_negated:
                return self._planned("ted_title", {"notice_id": notice_id}, notice_identifier_kind)
            if _contains_any(normalized, _TED_CHAIN_HINTS):
                if notice_id.casefold() not in self.current_ted_ids:
                    return self._abstain("notice_is_not_a_current_modification")
                return self._planned(
                    "ted_chain", {"current_notice_id": notice_id}, notice_identifier_kind
                )
            if wants_title:
                return self._planned("ted_title", {"notice_id": notice_id}, notice_identifier_kind)
            return self._abstain("unsupported_ted_intent")

        previous_matches = [
            canonical
            for normalized_name, canonical in self.previous_names
            if normalized_name in normalized
        ]
        if len(previous_matches) == 1 and _contains_any(normalized, _GLEIF_RESOLUTION_HINTS):
            return self._planned(
                "gleif_resolve_previous",
                {"previous_name": previous_matches[0]},
                "previous_legal_name",
            )
        if previous_matches:
            return self._abstain("ambiguous_previous_name")
        return self._abstain("unsupported_or_unresolved_query")
