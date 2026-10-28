#!/usr/bin/env python3
"""Generalization check: does name/title-similarity entity resolution hold up on an
independent, well-known public benchmark (DBLP-ACM), outside the 22 curated GLEIF pairs?

This is NOT a substitute for any of the three external blockers on Task 238
(independent hidden query log, two-human identity adjudication, authorized real
workflow). It is a supplementary, honestly-labeled stress test using a real academic
citation-matching benchmark (Leipzig DB Group, since 2010) to check whether the GLEIF
finding -- name-only similarity is unreliable without an authoritative crosswalk --
generalizes to a different domain and a much larger sample.

Dataset: https://dbs.uni-leipzig.de/research/projects/benchmark-datasets-for-entity-resolution
Files used: ACM.csv, DBLP2.csv, DBLP-ACM_perfectMapping.csv (public, citation metadata only,
no personal or business-sensitive data).
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

_TOKENS = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"a", "an", "the", "of", "for", "on", "in", "and", "to", "with"}


def _normalize(value: str) -> str:
    return " ".join(_TOKENS.findall(str(value or "").casefold()))


def _tokens(value: str) -> set[str]:
    return {t for t in _TOKENS.findall(str(value or "").casefold()) if t not in _STOPWORDS}


def _sequence_score(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _jaccard_score(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def _ensemble_score(a: str, b: str) -> float:
    return max(_sequence_score(a, b), _jaccard_score(a, b))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="latin-1", newline="") as fh:
        return list(csv.DictReader(fh))


def build_pairs(data_dir: Path, hard_negatives_per_positive: int, seed: int) -> list[dict[str, Any]]:
    acm = {r["id"]: r for r in load_csv(data_dir / "ACM.csv")}
    dblp = {r["id"]: r for r in load_csv(data_dir / "DBLP2.csv")}
    mapping = load_csv(data_dir / "DBLP-ACM_perfectMapping.csv")

    rng = random.Random(seed)
    by_venue_year: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rid, row in dblp.items():
        by_venue_year[(row.get("venue", ""), row.get("year", ""))].append(rid)

    pairs: list[dict[str, Any]] = []
    used_negative_ids: set[str] = set()
    for i, row in enumerate(mapping):
        acm_id, dblp_id = row["idACM"], row["idDBLP"]
        if acm_id not in acm or dblp_id not in dblp:
            continue
        acm_row, dblp_row = acm[acm_id], dblp[dblp_id]
        pairs.append(
            {
                "id": f"POS-{i:04d}",
                "label": "same",
                "name_a": acm_row["title"],
                "name_b": dblp_row["title"],
            }
        )
        # Hard negatives: same venue+year as the true DBLP match, different paper.
        key = (dblp_row.get("venue", ""), dblp_row.get("year", ""))
        candidates = [c for c in by_venue_year.get(key, []) if c != dblp_id and c not in used_negative_ids]
        rng.shuffle(candidates)
        for j, neg_id in enumerate(candidates[:hard_negatives_per_positive]):
            used_negative_ids.add(neg_id)
            pairs.append(
                {
                    "id": f"NEG-{i:04d}-{j}",
                    "label": "different",
                    "name_a": acm_row["title"],
                    "name_b": dblp[neg_id]["title"],
                }
            )
    return pairs


def _metrics(pairs: list[dict[str, Any]], predictions: dict[str, str]) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    for pair in pairs:
        pred = predictions[pair["id"]]
        if pair["label"] == "same" and pred == "same":
            tp += 1
        elif pair["label"] == "same":
            fn += 1
        elif pred == "same":
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negatives = sum(p["label"] == "different" for p in pairs)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_merge_rate": round(fp / (negatives or 1), 4),
    }


def threshold_sweep(pairs: list[dict[str, Any]], scorer: Callable[[str, str], float]) -> dict[str, Any]:
    scores = {p["id"]: scorer(p["name_a"], p["name_b"]) for p in pairs}
    rows = []
    for step in range(0, 21):
        threshold = step / 20
        preds = {p["id"]: ("same" if scores[p["id"]] >= threshold else "different") for p in pairs}
        rows.append({"threshold": threshold, **_metrics(pairs, preds)})
    best = max(rows, key=lambda r: (r["f1"], r["precision"], r["recall"]))
    qualifying = [r for r in rows if r["precision"] >= 0.98 and r["recall"] >= 0.90 and r["false_merge_rate"] <= 0.01]
    return {"best_f1": best, "qualifying_thresholds": qualifying, "thresholds": rows}


def main() -> int:
    data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dblp_acm")
    out = Path(
        sys.argv[2]
        if len(sys.argv) > 2
        else "docs/validation/ontology-v1/public-study/er_generalization_dblp_acm_v1.json"
    )
    pairs = build_pairs(data_dir, hard_negatives_per_positive=1, seed=42)
    same = sum(p["label"] == "same" for p in pairs)
    diff = sum(p["label"] == "different" for p in pairs)

    methods = {
        "sequence_similarity": threshold_sweep(pairs, _sequence_score),
        "token_jaccard_without_stopwords": threshold_sweep(pairs, _jaccard_score),
        "max_sequence_or_jaccard": threshold_sweep(pairs, _ensemble_score),
    }
    h4_targets = {"precision": 0.98, "recall": 0.90, "false_merge_rate": 0.01}
    report = {
        "schema": "yeying.research.er-generalization-check.v1",
        "disclaimer": (
            "本报告是对 DBLP-ACM（独立学术引文基准，Leipzig DB Group 自 2010 年维护，"
            "与 USAspending/TED/GLEIF 无关）的泛化检验，不替代 Task 238 的三项外部依赖"
            "（隐藏题集/真实 query log、两名非开发者独立评审、授权真实工作流）。"
        ),
        "dataset_source": "https://dbs.uni-leipzig.de/research/projects/benchmark-datasets-for-entity-resolution",
        "dataset_files": ["ACM.csv", "DBLP2.csv", "DBLP-ACM_perfectMapping.csv"],
        "pairs_total": len(pairs),
        "pairs_same": same,
        "pairs_different": diff,
        "h4_targets": h4_targets,
        "name_only_methods": {
            name: {
                "best_f1": m["best_f1"],
                "qualifying_threshold_count": len(m["qualifying_thresholds"]),
            }
            for name, m in methods.items()
        },
        "decision": {
            "any_name_only_threshold_meets_h4": any(m["qualifying_thresholds"] for m in methods.values()),
        },
        "limitations": [
            "This is title-string matching on academic citation records, not organization/company"
            " identity resolution; it tests whether the GLEIF finding generalizes across domains,"
            " not whether it applies directly to the ontology's business entities.",
            "Hard negatives are same-venue/same-year paper pairs, a stress-test construction,"
            " not a production prevalence estimate.",
            "Positive pairs come from the dataset's published gold mapping, an academic ground"
            " truth; it is not a substitute for the two-non-developer identity adjudication"
            " required by the research plan.",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"pairs={len(pairs)} same={same} different={diff}")
    for name, m in methods.items():
        b = m["best_f1"]
        print(f"{name}: best_f1={b['f1']:.3f} precision={b['precision']:.3f} "
              f"recall={b['recall']:.3f} false_merge_rate={b['false_merge_rate']:.3f} "
              f"H4_qualifying_thresholds={len(m['qualifying_thresholds'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
