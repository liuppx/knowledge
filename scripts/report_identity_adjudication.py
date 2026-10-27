#!/usr/bin/env python3
"""Summarize a completed identity-adjudication queue without inferring labels."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTCOMES = {
    "authoritative_crosswalk_confirmed",
    "candidate_requires_adjudication",
    "no_crosswalk_found_in_checked_sources",
    "ambiguous",
    "insufficient_evidence",
}
REVIEWER_PREFIXES = ("reviewer_a", "reviewer_b")


def _utc_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return None
    return parsed


def _duration(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    if not math.isfinite(result) or result < 0:
        return None
    return result


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def _time_summary(values: list[float], cases: int) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "total_seconds": round(sum(values), 3) if values else None,
        "mean_seconds": round(statistics.mean(values), 3) if values else None,
        "median_seconds": round(statistics.median(values), 3) if values else None,
        "p90_seconds": round(_percentile(values, 0.9), 3)
        if values
        else None,
        "minutes_per_100_cases": round(sum(values) / cases * 100 / 60, 3)
        if values and cases
        else None,
    }


def _review_complete(row: dict[str, str], prefix: str) -> tuple[bool, str | None]:
    outcome = row.get(f"{prefix}_outcome", "").strip()
    if not outcome:
        return False, None
    if outcome not in OUTCOMES:
        return False, f"unknown {prefix} outcome {outcome!r}"

    required = (
        f"{prefix}_id",
        f"{prefix}_resolution_method",
        f"{prefix}_evidence_uri",
        f"{prefix}_started_at_utc",
        f"{prefix}_submitted_at_utc",
        f"{prefix}_duration_seconds",
    )
    missing = [field for field in required if not row.get(field, "").strip()]
    started = _utc_timestamp(row.get(f"{prefix}_started_at_utc", ""))
    submitted = _utc_timestamp(row.get(f"{prefix}_submitted_at_utc", ""))
    duration = _duration(row.get(f"{prefix}_duration_seconds", ""))
    if missing:
        return False, f"incomplete {prefix} review; missing {', '.join(missing)}"
    if started is None or submitted is None:
        return False, f"invalid UTC timestamp for {prefix}"
    if submitted < started:
        return False, f"{prefix} submitted before it started"
    if duration is None:
        return False, f"invalid {prefix} duration_seconds"
    return True, None


def _adjudication_complete(row: dict[str, str]) -> tuple[bool, str | None]:
    outcome = row.get("final_outcome", "").strip()
    if not outcome:
        return False, None
    if outcome not in OUTCOMES:
        return False, f"unknown final_outcome {outcome!r}"
    required = (
        "adjudicator_id",
        "final_resolution_method",
        "final_evidence_uri",
        "adjudicated_at_utc",
        "adjudication_duration_seconds",
    )
    missing = [field for field in required if not row.get(field, "").strip()]
    if missing:
        return False, f"incomplete adjudication; missing {', '.join(missing)}"
    if _utc_timestamp(row.get("adjudicated_at_utc", "")) is None:
        return False, "invalid UTC timestamp for adjudication"
    if _duration(row.get("adjudication_duration_seconds", "")) is None:
        return False, "invalid adjudication_duration_seconds"
    return True, None


def _has_review_data(row: dict[str, str], prefix: str) -> bool:
    return any(
        row.get(f"{prefix}_{field}", "").strip()
        for field in (
            "id",
            "outcome",
            "resolution_method",
            "evidence_uri",
            "started_at_utc",
            "submitted_at_utc",
            "duration_seconds",
        )
    )


def _kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    if not labels_a:
        return None
    if len(labels_a) != len(labels_b):
        raise ValueError("paired labels must have equal length")
    count = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / count
    a_counts = Counter(labels_a)
    b_counts = Counter(labels_b)
    categories = set(a_counts) | set(b_counts)
    expected = sum(a_counts[label] * b_counts[label] for label in categories) / (count * count)
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def summarize_queue(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("queue has no cases")
    case_ids = [row.get("case_id", "").strip() for row in rows]
    issues: list[str] = []
    if any(not case_id for case_id in case_ids):
        issues.append("one or more rows have an empty case_id")
    duplicate_ids = sorted(
        case_id for case_id, count in Counter(case_ids).items() if case_id and count > 1
    )
    if duplicate_ids:
        issues.append(f"duplicate case_id values: {', '.join(duplicate_ids)}")

    complete: dict[str, list[dict[str, str]]] = {prefix: [] for prefix in REVIEWER_PREFIXES}
    partial_counts = Counter()
    reviewer_times: dict[str, list[float]] = {prefix: [] for prefix in REVIEWER_PREFIXES}
    adjudicated_rows: list[dict[str, str]] = []
    adjudication_times: list[float] = []
    paired_rows: list[dict[str, str]] = []
    for row in rows:
        case_id = row.get("case_id", "").strip() or "<empty>"
        row_complete = {}
        for prefix in REVIEWER_PREFIXES:
            is_complete, error = _review_complete(row, prefix)
            outcome = row.get(f"{prefix}_outcome", "").strip()
            any_review_data = _has_review_data(row, prefix)
            row_complete[prefix] = is_complete
            if is_complete:
                complete[prefix].append(row)
                reviewer_times[prefix].append(
                    _duration(row[f"{prefix}_duration_seconds"]) or 0.0
                )
            elif any_review_data:
                partial_counts[prefix] += 1
                if error:
                    issues.append(f"{case_id}: {error}")
                else:
                    issues.append(
                        f"{case_id}: partial {prefix} review fields "
                        "without a valid outcome"
                    )
            elif error:
                issues.append(f"{case_id}: {error}")

        if row_complete["reviewer_a"] and row_complete["reviewer_b"]:
            paired_rows.append(row)
            actual_disagreement = (
                row["reviewer_a_outcome"].strip()
                != row["reviewer_b_outcome"].strip()
            )
            declared = row.get("disagreement", "").strip().casefold()
            if declared:
                if declared not in {"true", "false", "yes", "no", "1", "0"}:
                    issues.append(f"{case_id}: invalid disagreement value {declared!r}")
                else:
                    declared_bool = declared in {"true", "yes", "1"}
                    if declared_bool != actual_disagreement:
                        issues.append(f"{case_id}: disagreement does not match reviewer outcomes")

        adjudicated, error = _adjudication_complete(row)
        if adjudicated:
            adjudicated_rows.append(row)
            adjudication_times.append(
                _duration(row["adjudication_duration_seconds"]) or 0.0
            )
        elif any(
            row.get(field, "").strip()
            for field in (
                "adjudicator_id",
                "final_outcome",
                "final_resolution_method",
                "final_evidence_uri",
                "adjudicated_at_utc",
                "adjudication_duration_seconds",
            )
        ):
            if error:
                issues.append(f"{case_id}: {error}")
            else:
                issues.append(f"{case_id}: partial adjudication fields without a valid outcome")

    labels_a = [row["reviewer_a_outcome"].strip() for row in paired_rows]
    labels_b = [row["reviewer_b_outcome"].strip() for row in paired_rows]
    agreements = sum(a == b for a, b in zip(labels_a, labels_b))
    disagreements = len(paired_rows) - agreements
    all_review_seconds = sum(sum(values) for values in reviewer_times.values())
    adjudicated_case_count = len(adjudicated_rows)
    return {
        "cases_total": len(rows),
        "cases_pending_both": sum(
            not _has_review_data(row, "reviewer_a")
            and not _has_review_data(row, "reviewer_b")
            for row in rows
        ),
        "reviewer_a_complete": len(complete["reviewer_a"]),
        "reviewer_a_partial": partial_counts["reviewer_a"],
        "reviewer_b_complete": len(complete["reviewer_b"]),
        "reviewer_b_partial": partial_counts["reviewer_b"],
        "paired_reviews_complete": len(paired_rows),
        "paired_review_completion_rate": round(len(paired_rows) / len(rows), 4),
        "adjudications_complete": adjudicated_case_count,
        "raw_agreement_count": agreements,
        "raw_agreement_rate": round(agreements / len(paired_rows), 4)
        if paired_rows
        else None,
        "disagreement_count": disagreements,
        "disagreement_rate": round(disagreements / len(paired_rows), 4)
        if paired_rows
        else None,
        "cohens_kappa": round(_kappa(labels_a, labels_b), 4)
        if paired_rows
        else None,
        "reviewer_a_outcomes": dict(
            sorted(
                Counter(
                    row["reviewer_a_outcome"].strip()
                    for row in complete["reviewer_a"]
                ).items()
            )
        ),
        "reviewer_b_outcomes": dict(
            sorted(
                Counter(
                    row["reviewer_b_outcome"].strip()
                    for row in complete["reviewer_b"]
                ).items()
            )
        ),
        "final_outcomes": dict(
            sorted(Counter(row["final_outcome"].strip() for row in adjudicated_rows).items())
        ),
        "reviewer_a_time": _time_summary(reviewer_times["reviewer_a"], len(complete["reviewer_a"])),
        "reviewer_b_time": _time_summary(reviewer_times["reviewer_b"], len(complete["reviewer_b"])),
        "combined_review_time": {
            **_time_summary(
                reviewer_times["reviewer_a"] + reviewer_times["reviewer_b"],
                len(paired_rows),
            ),
            "minutes_per_100_paired_cases": round(
                all_review_seconds / len(paired_rows) * 100 / 60, 3
            )
            if paired_rows
            else None,
        },
        "adjudication_time": _time_summary(adjudication_times, adjudicated_case_count),
        "data_quality_issues": issues,
    }


def load_queue(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"case_id", *(f"{prefix}_outcome" for prefix in REVIEWER_PREFIXES)}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"queue missing required columns: {', '.join(sorted(missing))}")
        return list(reader)


def render_markdown(report: dict[str, Any]) -> str:
    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1%}"

    def time_value(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1f}s"

    def numeric_value(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1f}"

    combined = report["combined_review_time"]
    lines = [
        "# Identity Adjudication Queue Report",
        "",
        f"- Cases: {report['cases_total']}",
        f"- Paired reviews complete: {report['paired_reviews_complete']} "
        f"({pct(report['paired_review_completion_rate'])})",
        f"- Pending both reviewers: {report['cases_pending_both']}",
        f"- Partial reviews: A={report['reviewer_a_partial']}, B={report['reviewer_b_partial']}",
        f"- Final adjudications complete: {report['adjudications_complete']}",
        f"- Raw agreement: {report['raw_agreement_count']} ({pct(report['raw_agreement_rate'])})",
        f"- Disagreements: {report['disagreement_count']} ({pct(report['disagreement_rate'])})",
        f"- Cohen's kappa: "
        f"{report['cohens_kappa'] if report['cohens_kappa'] is not None else 'n/a'}",
        f"- Combined review time: {time_value(combined['total_seconds'])} total; "
        f"{numeric_value(combined['minutes_per_100_paired_cases'])} minutes per 100 paired cases",
        "- Reviewer A mean / median / P90: "
        f"{time_value(report['reviewer_a_time']['mean_seconds'])} / "
        f"{time_value(report['reviewer_a_time']['median_seconds'])} / "
        f"{time_value(report['reviewer_a_time']['p90_seconds'])}",
        "- Reviewer B mean / median / P90: "
        f"{time_value(report['reviewer_b_time']['mean_seconds'])} / "
        f"{time_value(report['reviewer_b_time']['median_seconds'])} / "
        f"{time_value(report['reviewer_b_time']['p90_seconds'])}",
        "- Adjudication mean / median / P90: "
        f"{time_value(report['adjudication_time']['mean_seconds'])} / "
        f"{time_value(report['adjudication_time']['median_seconds'])} / "
        f"{time_value(report['adjudication_time']['p90_seconds'])}",
        "",
        "## Data Quality",
        "",
    ]
    if report["data_quality_issues"]:
        lines.extend(f"- {issue}" for issue in report["data_quality_issues"])
    else:
        lines.append("- No detected issues.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "queue",
        nargs="?",
        type=Path,
        default=Path(
            "docs/validation/ontology-v1/public-study/identity_adjudication_queue_v1.csv"
        ),
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = summarize_queue(load_queue(args.queue))
    except (OSError, ValueError, csv.Error) as exc:
        print(f"identity adjudication report failed: {exc}", file=sys.stderr)
        return 1
    output = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.format == "json"
        else render_markdown(report)
    )
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["data_quality_issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
