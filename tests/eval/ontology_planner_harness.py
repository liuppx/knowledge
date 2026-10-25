"""Evaluation harness for the frozen C3 natural-language planner challenge."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from tests.eval.ontology_planner import DeterministicSourcePlanner
from tests.eval.ontology_public_harness import (
    DEFAULT_CACHE_DIR,
    DEFAULT_REPORT_DIR,
    SourceNativeToolView,
    load_public_records,
)


CHALLENGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "validation"
    / "ontology-v1"
    / "public-study"
    / "planner_challenge_v1.json"
)
EXPECTED_CHALLENGE_SHA256 = "b87251e223472c1f69fd15fa9128c437a700338ad5f0bf5274d8f0ea09032cc1"


def _source_for_operation(operation: str) -> str:
    if operation.startswith("usa_"):
        return "usa"
    if operation.startswith("ted_"):
        return "ted"
    if operation.startswith("gleif_"):
        return "gleif"
    raise ValueError(f"unknown operation {operation}")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / (denominator or 1), 4)


def _evaluate_cases(
    cases: list[dict[str, Any]],
    planner: DeterministicSourcePlanner,
    source_tools: SourceNativeToolView,
) -> tuple[dict[str, Any], dict[str, Any]]:
    per_case: dict[str, Any] = {}
    answer_cases = [case for case in cases if case["expected_resolution"] == "answer"]
    abstain_cases = [case for case in cases if case["expected_resolution"] == "abstain"]
    operation_correct = 0
    params_correct = 0
    abstention_correct = 0
    end_to_end_correct = 0
    evidence_correct = 0
    source_totals: Counter = Counter()
    source_params_correct: Counter = Counter()

    for case in cases:
        result = planner.plan(case["query"])
        operation_match = result["operation"] == case["expected_operation"]
        params_match = result["params"] == case["expected_params"]
        abstention_match = case["expected_resolution"] == "abstain" and result["status"] == "abstain"
        e2e_match = False
        evidence_match = False

        if case["expected_resolution"] == "answer":
            operation_correct += int(operation_match)
            params_correct += int(operation_match and params_match)
            source = _source_for_operation(case["expected_operation"])
            source_totals[source] += 1
            source_params_correct[source] += int(operation_match and params_match)
            oracle_answer, oracle_evidence = source_tools.answer(
                case["expected_operation"], case["expected_params"]
            )
            if result["status"] == "planned":
                try:
                    planned_answer, planned_evidence = source_tools.answer(
                        result["operation"], result["params"]
                    )
                except (KeyError, TypeError, ValueError):
                    planned_answer, planned_evidence = {"status": "planner_error", "value": None}, []
                e2e_match = planned_answer == oracle_answer
                evidence_match = sorted(planned_evidence) == sorted(oracle_evidence)
            end_to_end_correct += int(e2e_match)
            evidence_correct += int(evidence_match)
        else:
            abstention_correct += int(abstention_match)

        per_case[case["id"]] = {
            "split": case["split"],
            "stratum": case["stratum"],
            "query": case["query"],
            "expected_operation": case["expected_operation"],
            "expected_params": case["expected_params"],
            "planner": result,
            "operation_match": operation_match,
            "params_match": params_match,
            "abstention_match": abstention_match,
            "end_to_end_answer_match": e2e_match,
            "evidence_match": evidence_match,
        }

    metrics = {
        "cases": len(cases),
        "answer_cases": len(answer_cases),
        "abstain_cases": len(abstain_cases),
        "operation_accuracy": _ratio(operation_correct, len(answer_cases)),
        "exact_parameter_match": _ratio(params_correct, len(answer_cases)),
        "abstention": _ratio(abstention_correct, len(abstain_cases)),
        "false_merge_count": len(abstain_cases) - abstention_correct,
        "end_to_end_answer_accuracy": _ratio(end_to_end_correct, len(answer_cases)),
        "evidence_traceability": _ratio(evidence_correct, len(answer_cases)),
        "source_exact_parameter_match": {
            source: _ratio(source_params_correct[source], total)
            for source, total in sorted(source_totals.items())
        },
    }
    return metrics, per_case


def run_planner_challenge(
    report_dir: Path | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    challenge_bytes = CHALLENGE_PATH.read_bytes()
    challenge_hash = hashlib.sha256(challenge_bytes).hexdigest()
    if challenge_hash != EXPECTED_CHALLENGE_SHA256:
        raise AssertionError(
            f"planner challenge drift: expected {EXPECTED_CHALLENGE_SHA256}, got {challenge_hash}"
        )
    challenge = json.loads(challenge_bytes)
    records = load_public_records(
        cache_dir or Path(os.environ.get("KNOWLEDGE_ONTOLOGY_EVAL_CACHE_DIR", DEFAULT_CACHE_DIR))
    )
    planner = DeterministicSourcePlanner(records)
    source_tools = SourceNativeToolView(records)
    cases = challenge["cases"]
    development = [case for case in cases if case["split"] == "development"]
    test = [case for case in cases if case["split"] == "test"]
    all_metrics, per_case = _evaluate_cases(cases, planner, source_tools)
    development_metrics, _ = _evaluate_cases(development, planner, source_tools)
    test_metrics, _ = _evaluate_cases(test, planner, source_tools)
    thresholds = {
        "operation_accuracy": 0.95,
        "exact_parameter_match": 0.90,
        "source_exact_parameter_match": 0.80,
        "abstention": 1.0,
        "false_merge_count": 0,
        "end_to_end_answer_accuracy": 0.90,
        "evidence_traceability": 1.0,
    }
    gates = {
        "operation_accuracy": test_metrics["operation_accuracy"] >= thresholds["operation_accuracy"],
        "exact_parameter_match": test_metrics["exact_parameter_match"]
        >= thresholds["exact_parameter_match"],
        "source_exact_parameter_match": all(
            value >= thresholds["source_exact_parameter_match"]
            for value in test_metrics["source_exact_parameter_match"].values()
        ),
        "abstention": test_metrics["abstention"] == thresholds["abstention"],
        "false_merge_count": test_metrics["false_merge_count"] == thresholds["false_merge_count"],
        "end_to_end_answer_accuracy": test_metrics["end_to_end_answer_accuracy"]
        >= thresholds["end_to_end_answer_accuracy"],
        "evidence_traceability": test_metrics["evidence_traceability"]
        == thresholds["evidence_traceability"],
    }
    report = {
        "challenge_version": challenge["version"],
        "challenge_sha256": challenge_hash,
        "planner": "deterministic exact-identifier and intent rules; no label file access at runtime",
        "metrics": {
            "all": all_metrics,
            "development": development_metrics,
            "test": test_metrics,
        },
        "thresholds": thresholds,
        "gates": gates,
        "passed": all(gates.values()),
        "limitations": [
            "The committed challenge is visible to implementers and is not an externally held hidden set.",
            "Queries are authored from public records rather than sampled from real user logs.",
            "The deterministic planner is a transparent baseline, not a live model-quality result.",
        ],
        "cases": per_case,
    }
    destination = report_dir or Path(os.environ.get("KNOWLEDGE_EVAL_REPORT_DIR", DEFAULT_REPORT_DIR))
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "ontology_planner_challenge.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (destination / "ontology_planner_challenge.md").write_text(
        render_planner_markdown(report), encoding="utf-8"
    )
    return report


def render_planner_markdown(report: dict[str, Any]) -> str:
    test = report["metrics"]["test"]
    lines = [
        "## C3 planner frozen challenge",
        "",
        f"- challenge: `{report['challenge_version']}`",
        f"- SHA-256: `{report['challenge_sha256']}`",
        f"- planner: `{report['planner']}`",
        f"- test cases: {test['cases']} ({test['answer_cases']} answer / {test['abstain_cases']} abstain)",
        "",
        "| metric | result |",
        "| --- | ---: |",
        f"| operation accuracy | {test['operation_accuracy']:.1%} |",
        f"| exact parameter match | {test['exact_parameter_match']:.1%} |",
        f"| negative abstention | {test['abstention']:.1%} |",
        f"| false merges | {test['false_merge_count']} |",
        f"| planner + C3 answer accuracy | {test['end_to_end_answer_accuracy']:.1%} |",
        f"| Evidence traceability | {test['evidence_traceability']:.1%} |",
        "",
        f"- source parameter match: `{test['source_exact_parameter_match']}`",
        f"- gates: `{report['gates']}`",
        f"- passed: `{report['passed']}`",
        "",
        "This is a frozen, committed challenge—not an externally held hidden test or a live-model result.",
        "",
    ]
    return "\n".join(lines)
