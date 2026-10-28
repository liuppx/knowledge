#!/usr/bin/env python3
"""Tool-assisted public crosswalk reference probe for the identity queue.

This is NOT the independent two-reviewer study. It performs a single deterministic
pass of public GLEIF API lookups for each queue row and records, with evidence URIs,
whether an authoritative source-ID -> LEI crosswalk is observable. Output is a
reference artifact only; it must never be copied into reviewer_* columns.
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GLEIF = "https://api.gleif.org/api/v1/lei-records"
HEADERS = {"Accept": "application/vnd.api+json", "User-Agent": "yeying-knowledge-research/1.0"}


def _get(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _records(params: dict[str, str]) -> tuple[list[dict[str, Any]], int, str]:
    """Return (records_on_page, pagination_total, url).

    GLEIF's filter[entity.legalName] is not an exact match: when nothing matches
    closely it can return the full collection (large total). Callers MUST use the
    pagination total, not len(records), to decide whether a filter really matched.
    """
    query = urllib.parse.urlencode(params, safe="")
    url = f"{GLEIF}?{query}"
    try:
        payload = _get(url)
    except Exception as exc:  # noqa: BLE001 - record the failure, keep going
        return [], -1, f"{url}  (error: {exc})"
    total = payload.get("meta", {}).get("pagination", {}).get("total", -1)
    return (payload.get("data", []) or [], total, url)


def _summ(rec: dict[str, Any]) -> dict[str, Any]:
    a = rec.get("attributes", {})
    ent = a.get("entity", {})
    return {
        "lei": a.get("lei"),
        "legal_name": ent.get("legalName", {}).get("name"),
        "country": ent.get("legalAddress", {}).get("country"),
        "registered_as": ent.get("registeredAs"),
        "registered_at": ent.get("registeredAt", {}).get("id"),
        "status": ent.get("status"),
    }


def probe_row(row: dict[str, str]) -> dict[str, Any]:
    sid = row["source_identifier"].strip()
    name = row["source_name"].strip()
    role = row["source_role"].strip()
    ns = row["identifier_namespace_status"].strip()
    evidence: list[str] = []
    checks: list[dict[str, Any]] = []

    # Bulgarian UIC (RA000065 confirmed): authoritative registeredAs lookup.
    if ns == "authoritative_ra000065_confirmed_by_registry" or sid.isdigit():
        recs, total, url = _records(
            {"filter[entity.registeredAs]": sid, "filter[entity.legalAddress.country]": "BG",
             "page[size]": "5"}
        )
        evidence.append(url)
        checks.append({"method": "gleif registeredAs==UIC & country==BG",
                       "total": total, "page_records": [_summ(r) for r in recs]})

    # US recipient (UEI): GLEIF keys on state reg number, not UEI -> name lookup only.
    if role == "usa_recipient":
        recs, total, url = _records(
            {"filter[entity.legalName]": name, "filter[entity.legalAddress.country]": "US",
             "page[size]": "5"}
        )
        evidence.append(url)
        checks.append({"method": "gleif legalName (US); UEI is NOT a GLEIF key",
                       "total": total, "page_records": [_summ(r) for r in recs]})

    # Generic name probe for the remaining TED buyers/winners with no exposed ID.
    if not checks:
        recs, total, url = _records({"filter[entity.legalName]": name, "page[size]": "5"})
        evidence.append(url)
        checks.append({"method": "gleif legalName (any country)",
                       "total": total, "page_records": [_summ(r) for r in recs]})

    # Classify conservatively: authoritative only if exactly one hit whose
    # registeredAs matches the source id; otherwise candidate / none / ambiguous.
    classification = _classify(sid, role, ns, name, checks)
    return {
        "case_id": row["case_id"].strip(),
        "source_role": role,
        "source_name": name,
        "source_identifier": sid,
        "namespace_status": ns,
        "classification": classification,
        "checks": checks,
        "evidence_uris": evidence,
    }


def _norm(text: str | None) -> str:
    return " ".join((text or "").strip().casefold().replace(",", " ").split())


def _classify(sid: str, role: str, ns: str, name: str, checks: list[dict[str, Any]]) -> str:
    primary = checks[0]
    total = primary.get("total", -1)
    recs = primary["page_records"]
    if total < 0:
        return "insufficient_evidence"  # the lookup itself failed

    if ns == "authoritative_ra000065_confirmed_by_registry" or sid.isdigit():
        # BG path: authoritative crosswalk requires a GLEIF record whose registeredAs==UIC.
        # GLEIF's registeredAs filter is reliable; a large total would mean no real match.
        exact = [r for r in recs if (r.get("registered_as") or "") == sid]
        if total == 1 and len(exact) == 1:
            return "authoritative_crosswalk_confirmed"
        if len(exact) > 1:
            return "ambiguous"
        return "no_crosswalk_found_in_checked_sources"

    # Name-only paths can never be authoritative on their own, and GLEIF's
    # legalName filter returns the whole collection when nothing matches.
    # Treat only a small total with an actual name match as a candidate.
    target = _norm(name)
    name_matches = [r for r in recs if _norm(r.get("legal_name")) == target]
    if total == 0 or total > 50:
        # total>50 means the filter did not narrow -> no genuine exact match.
        return "no_crosswalk_found_in_checked_sources"
    if len(name_matches) == 1 and total <= 5:
        return "candidate_requires_adjudication"
    if len(name_matches) > 1:
        return "ambiguous"
    if 0 < total <= 50:
        return "candidate_requires_adjudication"
    return "no_crosswalk_found_in_checked_sources"


def main() -> int:
    queue = Path(
        sys.argv[1] if len(sys.argv) > 1
        else "docs/validation/ontology-v1/public-study/identity_adjudication_queue_v1.csv"
    )
    out = Path(sys.argv[2] if len(sys.argv) > 2
               else "docs/validation/ontology-v1/public-study/identity_crosswalk_reference_v1.json")
    with queue.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    results = []
    for row in rows:
        results.append(probe_row(row))
        time.sleep(0.4)  # be polite to the public API
    tally: dict[str, int] = {}
    for r in results:
        tally[r["classification"]] = tally.get(r["classification"], 0) + 1
    report = {
        "schema": "yeying.research.identity-crosswalk-reference.v1",
        "disclaimer": "单次工具辅助公开查询参考件，非两名评审者的独立裁决；不得写入 reviewer_* 列，不得外推真实业务成本。",
        "source_queue": str(queue),
        "gleif_api": GLEIF,
        "generated_cases": len(results),
        "classification_tally": tally,
        "results": results,
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}  cases={len(results)}  tally={tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
