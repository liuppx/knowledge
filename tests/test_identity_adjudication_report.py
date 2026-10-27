from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.report_identity_adjudication import load_queue, summarize_queue


ROOT = Path(__file__).resolve().parents[1]
QUEUE = (
    ROOT
    / "docs"
    / "validation"
    / "ontology-v1"
    / "public-study"
    / "identity_adjudication_queue_v1.csv"
)


def completed_review(prefix: str, outcome: str, duration: int) -> dict[str, str]:
    return {
        f"{prefix}_id": f"{prefix}-reviewer",
        f"{prefix}_outcome": outcome,
        f"{prefix}_resolution_method": "registry lookup",
        f"{prefix}_evidence_uri": "https://example.test/record/1",
        f"{prefix}_started_at_utc": "2026-10-27T10:00:00Z",
        f"{prefix}_submitted_at_utc": "2026-10-27T10:01:00Z",
        f"{prefix}_duration_seconds": str(duration),
    }


def base_row(case_id: str) -> dict[str, str]:
    row = {"case_id": case_id, "status": "pending", "disagreement": ""}
    for prefix in ("reviewer_a", "reviewer_b"):
        row.update(
            {
                f"{prefix}_{field}": ""
                for field in (
                    "id",
                    "outcome",
                    "resolution_method",
                    "evidence_uri",
                    "started_at_utc",
                    "submitted_at_utc",
                    "duration_seconds",
                )
            }
        )
    row.update(
        {
            "adjudicator_id": "",
            "final_outcome": "",
            "final_resolution_method": "",
            "final_evidence_uri": "",
            "adjudicated_at_utc": "",
            "adjudication_duration_seconds": "",
        }
    )
    return row


def test_unfilled_queue_is_reported_as_pending_not_as_no_match():
    report = summarize_queue(load_queue(QUEUE))

    assert report["cases_total"] == 29
    assert report["cases_pending_both"] == 29
    assert report["paired_reviews_complete"] == 0
    assert report["raw_agreement_rate"] is None
    assert report["cohens_kappa"] is None
    assert report["reviewer_a_outcomes"] == {}
    assert report["data_quality_issues"] == []


def test_report_computes_nominal_kappa_and_time_costs():
    row_a = base_row("R001")
    row_a.update(completed_review("reviewer_a", "authoritative_crosswalk_confirmed", 60))
    row_a.update(completed_review("reviewer_b", "authoritative_crosswalk_confirmed", 90))
    row_a.update(
        {
            "adjudicator_id": "adjudicator",
            "final_outcome": "authoritative_crosswalk_confirmed",
            "final_resolution_method": "source crosswalk",
            "final_evidence_uri": "https://example.test/final/1",
            "adjudicated_at_utc": "2026-10-27T11:00:00Z",
            "adjudication_duration_seconds": "45",
        }
    )

    row_b = base_row("R002")
    row_b.update(completed_review("reviewer_a", "ambiguous", 120))
    row_b.update(completed_review("reviewer_b", "insufficient_evidence", 150))
    row_b["disagreement"] = "true"
    row_c = base_row("R003")

    report = summarize_queue([row_a, row_b, row_c])

    assert report["paired_reviews_complete"] == 2
    assert report["raw_agreement_count"] == 1
    assert report["raw_agreement_rate"] == 0.5
    assert report["disagreement_count"] == 1
    assert report["cohens_kappa"] == pytest.approx(1 / 3, abs=0.0001)
    assert report["reviewer_a_time"]["total_seconds"] == 180
    assert report["reviewer_b_time"]["total_seconds"] == 240
    assert report["combined_review_time"]["minutes_per_100_paired_cases"] == 350
    assert report["adjudications_complete"] == 1
    assert report["adjudication_time"]["minutes_per_100_cases"] == 75
    assert report["data_quality_issues"] == []


def test_partial_and_invalid_review_data_is_excluded_and_reported():
    row = base_row("R001")
    row.update(completed_review("reviewer_a", "some_unsupported_label", 60))
    row["reviewer_b_outcome"] = "ambiguous"
    row["reviewer_b_id"] = "reviewer-b"
    row["reviewer_b_duration_seconds"] = "-5"

    report = summarize_queue([row])

    assert report["reviewer_a_complete"] == 0
    assert report["reviewer_b_complete"] == 0
    assert report["paired_reviews_complete"] == 0
    assert len(report["data_quality_issues"]) >= 2
    assert any("unknown reviewer_a outcome" in item for item in report["data_quality_issues"])
    assert any("incomplete reviewer_b review" in item for item in report["data_quality_issues"])


def test_declared_disagreement_must_match_independent_labels():
    row = base_row("R001")
    row.update(completed_review("reviewer_a", "ambiguous", 10))
    row.update(completed_review("reviewer_b", "ambiguous", 10))
    row["disagreement"] = "true"

    report = summarize_queue([row])

    assert report["raw_agreement_rate"] == 1.0
    assert any("disagreement does not match" in item for item in report["data_quality_issues"])


def test_unlabeled_partial_review_is_not_reported_as_a_pending_empty_case():
    row = base_row("R001")
    row["reviewer_a_id"] = "reviewer-a"
    row["reviewer_a_started_at_utc"] = "2026-10-27T10:00:00Z"

    report = summarize_queue([row])

    assert report["cases_pending_both"] == 0
    assert report["reviewer_a_partial"] == 1
    assert any("partial reviewer_a review fields" in item for item in report["data_quality_issues"])


def test_cli_writes_machine_readable_report(tmp_path: Path):
    output_path = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "report_identity_adjudication.py"),
            str(QUEUE),
            "--format",
            "json",
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["cases_pending_both"] == 29


def test_load_queue_rejects_missing_required_columns(tmp_path: Path):
    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["case_id"])
        writer.writeheader()
        writer.writerow({"case_id": "R001"})

    with pytest.raises(ValueError, match="missing required columns"):
        load_queue(path)
