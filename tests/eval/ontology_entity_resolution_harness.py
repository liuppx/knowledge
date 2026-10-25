"""GLEIF-backed entity-resolution stress test for ontology V1."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from tests.eval.ontology_public_harness import (
    DEFAULT_CACHE_DIR,
    DEFAULT_REPORT_DIR,
    _request_json,
    _sha256_json,
)


PAIR_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "validation"
    / "ontology-v1"
    / "public-study"
    / "entity_resolution_pairs_v1.json"
)
EXPECTED_PAIR_SHA256 = "0d1f07953ffa1474365e4ec3365512908534cf02a64781a617f6195dfa9d7d9d"
EXPECTED_GLEIF_SOURCE_SHA256 = "a93e030095ca674431833783aa6cdbb0f85902a50ddfa24d85fad7ab7f67e7e9"
_TOKENS = re.compile(r"[a-z0-9]+")
_LEGAL_SUFFIXES = {
    "ab",
    "ag",
    "aktiebolag",
    "corp",
    "corporation",
    "company",
    "gmbh",
    "inc",
    "limited",
    "llc",
    "ltd",
    "plc",
    "private",
    "the",
}


def _normalize_name(value: str) -> str:
    return " ".join(_TOKENS.findall(str(value or "").casefold()))


def _name_tokens(value: str) -> set[str]:
    return {token for token in _TOKENS.findall(str(value or "").casefold()) if token not in _LEGAL_SUFFIXES}


def _sequence_score(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_name(left), _normalize_name(right)).ratio()


def _jaccard_score(left: str, right: str) -> float:
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _ensemble_score(left: str, right: str) -> float:
    return max(_sequence_score(left, right), _jaccard_score(left, right))


def _fetch_lei_record(lei: str, cache_dir: Path) -> dict[str, Any]:
    response = _request_json(f"https://api.gleif.org/api/v1/lei-records/{lei}", cache_dir=cache_dir)
    attributes = response["data"]["attributes"]
    entity = attributes["entity"]
    return {
        "lei": attributes["lei"],
        "legal_name": entity["legalName"]["name"],
        "previous_names": sorted(
            item["name"]
            for item in entity.get("otherNames", [])
            if item.get("type") == "PREVIOUS_LEGAL_NAME"
        ),
        "registration_status": attributes["registration"]["status"],
    }


def _classification_metrics(pairs: list[dict[str, Any]], predictions: dict[str, str]) -> dict[str, Any]:
    tp = fp = fn = tn = uncertain = 0
    for pair in pairs:
        prediction = predictions[pair["id"]]
        if prediction == "uncertain":
            uncertain += 1
            if pair["label"] == "same":
                fn += 1
            continue
        if pair["label"] == "same" and prediction == "same":
            tp += 1
        elif pair["label"] == "same":
            fn += 1
        elif prediction == "same":
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negatives = sum(pair["label"] == "different" for pair in pairs)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "uncertain": uncertain,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_merge_rate": round(fp / (negatives or 1), 4),
        "coverage": round((len(pairs) - uncertain) / (len(pairs) or 1), 4),
    }


def _threshold_sweep(
    pairs: list[dict[str, Any]],
    scorer: Callable[[str, str], float],
) -> dict[str, Any]:
    scores = {pair["id"]: scorer(pair["name_a"], pair["name_b"]) for pair in pairs}
    rows = []
    for step in range(0, 21):
        threshold = step / 20
        predictions = {
            pair["id"]: "same" if scores[pair["id"]] >= threshold else "different"
            for pair in pairs
        }
        metrics = _classification_metrics(pairs, predictions)
        rows.append({"threshold": threshold, **metrics})
    best = max(rows, key=lambda row: (row["f1"], row["precision"], row["recall"]))
    positive_scores = [scores[pair["id"]] for pair in pairs if pair["label"] == "same"]
    negative_scores = [scores[pair["id"]] for pair in pairs if pair["label"] == "different"]
    qualifying = [
        row
        for row in rows
        if row["precision"] >= 0.98
        and row["recall"] >= 0.90
        and row["false_merge_rate"] <= 0.01
    ]
    return {
        "scores": {key: round(value, 4) for key, value in scores.items()},
        "min_positive_score": round(min(positive_scores), 4),
        "max_negative_score": round(max(negative_scores), 4),
        "ranking_inversion": max(negative_scores) > min(positive_scores),
        "best_f1": best,
        "qualifying_thresholds": qualifying,
        "thresholds": rows,
    }


def _crosswalk_predictions(
    pairs: list[dict[str, Any]], records: dict[str, dict[str, Any]]
) -> dict[str, str]:
    alias_to_leis: dict[str, set[str]] = defaultdict(set)
    for record in records.values():
        for name in (record["legal_name"], *record["previous_names"]):
            alias_to_leis[_normalize_name(name)].add(record["lei"])
    predictions: dict[str, str] = {}
    for pair in pairs:
        left = alias_to_leis[_normalize_name(pair["name_a"])]
        right = alias_to_leis[_normalize_name(pair["name_b"])]
        if len(left) != 1 or len(right) != 1:
            predictions[pair["id"]] = "uncertain"
        else:
            predictions[pair["id"]] = "same" if left == right else "different"
    return predictions


def run_entity_resolution_eval(
    report_dir: Path | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    pair_bytes = PAIR_PATH.read_bytes()
    pair_hash = hashlib.sha256(pair_bytes).hexdigest()
    if pair_hash != EXPECTED_PAIR_SHA256:
        raise AssertionError(f"entity pair drift: expected {EXPECTED_PAIR_SHA256}, got {pair_hash}")
    dataset = json.loads(pair_bytes)
    pairs = dataset["pairs"]
    leis = sorted({pair["lei_a"] for pair in pairs} | {pair["lei_b"] for pair in pairs})
    selected_cache = cache_dir or Path(
        os.environ.get("KNOWLEDGE_ONTOLOGY_EVAL_CACHE_DIR", DEFAULT_CACHE_DIR)
    )
    records = {lei: _fetch_lei_record(lei, selected_cache) for lei in leis}

    source_mismatches: list[dict[str, str]] = []
    for pair in pairs:
        for suffix in ("a", "b"):
            lei = pair[f"lei_{suffix}"]
            name = pair[f"name_{suffix}"]
            official_names = {records[lei]["legal_name"], *records[lei]["previous_names"]}
            if name not in official_names:
                source_mismatches.append({"pair": pair["id"], "lei": lei, "name": name})
    if source_mismatches:
        raise AssertionError(f"GLEIF source drift: {source_mismatches}")
    source_hash = _sha256_json(records)
    if source_hash != EXPECTED_GLEIF_SOURCE_SHA256:
        raise AssertionError(
            f"GLEIF normalized source drift: expected {EXPECTED_GLEIF_SOURCE_SHA256}, got {source_hash}"
        )

    methods = {
        "sequence_similarity": _threshold_sweep(pairs, _sequence_score),
        "token_jaccard_without_legal_suffixes": _threshold_sweep(pairs, _jaccard_score),
        "max_sequence_or_jaccard": _threshold_sweep(pairs, _ensemble_score),
    }
    crosswalk = _classification_metrics(pairs, _crosswalk_predictions(pairs, records))
    h4_targets = {"precision": 0.98, "recall": 0.90, "false_merge_rate": 0.01}
    report = {
        "dataset_version": dataset["version"],
        "pair_sha256": pair_hash,
        "normalized_gleif_source_sha256": source_hash,
        "dataset": {
            "pairs": len(pairs),
            "same": sum(pair["label"] == "same" for pair in pairs),
            "different": sum(pair["label"] == "different" for pair in pairs),
            "unique_leis": len(leis),
            "all_registration_statuses": sorted({record["registration_status"] for record in records.values()}),
        },
        "h4_targets": h4_targets,
        "name_only_methods": methods,
        "authoritative_alias_to_lei_crosswalk": crosswalk,
        "decision": {
            "any_name_only_threshold_meets_h4": any(
                method["qualifying_thresholds"] for method in methods.values()
            ),
            "crosswalk_meets_h4": (
                crosswalk["precision"] >= h4_targets["precision"]
                and crosswalk["recall"] >= h4_targets["recall"]
                and crosswalk["false_merge_rate"] <= h4_targets["false_merge_rate"]
            ),
            "verdict": "require_stable_id_crosswalk_and_human_review_for_unresolved",
        },
        "limitations": dataset["limitations"]
        + [
            "The authoritative crosswalk result is an upper bound because every sampled name is present in GLEIF.",
            "Name-only threshold results are stress-test counterexamples, not production prevalence estimates.",
        ],
        "pairs": pairs,
    }
    destination = report_dir or Path(os.environ.get("KNOWLEDGE_EVAL_REPORT_DIR", DEFAULT_REPORT_DIR))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "ontology_entity_resolution.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (destination / "ontology_entity_resolution.md").write_text(
        render_entity_resolution_markdown(report), encoding="utf-8"
    )
    return report


def render_entity_resolution_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    lines = [
        "## GLEIF entity-resolution stress test",
        "",
        f"- pairs: {dataset['pairs']} ({dataset['same']} same / {dataset['different']} different)",
        f"- unique LEIs: {dataset['unique_leis']}",
        f"- pair SHA-256: `{report['pair_sha256']}`",
        f"- source SHA-256: `{report['normalized_gleif_source_sha256']}`",
        "",
        "| method | best F1 | precision | recall | false merge | H4 threshold exists |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, method in report["name_only_methods"].items():
        best = method["best_f1"]
        lines.append(
            f"| {name} | {best['f1']:.1%} | {best['precision']:.1%} | {best['recall']:.1%} "
            f"| {best['false_merge_rate']:.1%} | {'yes' if method['qualifying_thresholds'] else 'no'} |"
        )
    crosswalk = report["authoritative_alias_to_lei_crosswalk"]
    lines += [
        f"| authoritative alias→LEI crosswalk | {crosswalk['f1']:.1%} | {crosswalk['precision']:.1%} "
        f"| {crosswalk['recall']:.1%} | {crosswalk['false_merge_rate']:.1%} | yes |",
        "",
        f"- name-only method clears H4: `{report['decision']['any_name_only_threshold_meets_h4']}`",
        f"- crosswalk clears H4: `{report['decision']['crosswalk_meets_h4']}`",
        f"- verdict: `{report['decision']['verdict']}`",
        "",
    ]
    return "\n".join(lines)
