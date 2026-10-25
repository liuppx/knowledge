#!/usr/bin/env bash
# Unified test entrypoint (see 夜莺社区/工程/自动化测试脚本规范.md).
# Adapts the community `scripts/test.sh --suite {suite}` contract to pytest and
# the Alembic/OpenAPI drift gates.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

SUITE="unit"
QUIET=0
PYTEST_EXTRA=()

usage() {
  cat <<'EOF'
Usage: scripts/test.sh [--suite {unit|integration|smoke|eval|ontology-eval|all}] [--quiet] [--help]

Suites:
  unit         pytest test suite (default). Requires PostgreSQL.
  integration  Alembic drift check + full pytest suite.
  smoke        Fast subset: config guard + OpenAPI contract gates.
  eval         Q01–Q12 retrieval quality report (tests/eval, writes .eval/).
  ontology-eval  Public USAspending/TED/GLEIF ontology proxy pilot (networked).
  all          integration suite (Alembic drift + full pytest).

Environment:
  TEST_DATABASE_URL  DB for pytest      (default: knowledge_test on localhost)
  DATABASE_URL       DB for alembic check (default: TEST_DATABASE_URL)
  KNOWLEDGE_EVAL_PROVIDER    eval providers: offline (default) | live (real gateway)
  KNOWLEDGE_EVAL_REPORT_DIR  eval report output dir (default: .eval)
  KNOWLEDGE_ONTOLOGY_EVAL_CACHE_DIR  public API cache (default: /tmp/knowledge-public-ontology-pilot-cache)
  KNOWLEDGE_TED_XML_CACHE_DIR  optional official TED XML cache for source revalidation
  KNOWLEDGE_ONTOLOGY_EVAL_REFRESH    set to 1 to bypass cached API responses
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite) SUITE="${2:?--suite requires a value}"; shift 2 ;;
    --suite=*) SUITE="${1#*=}"; shift ;;
    --quiet) QUIET=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# Prefer the project venv, fall back to python3 on PATH.
if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PY="${ROOT_DIR}/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql://knowledge:knowledge@127.0.0.1:5432/knowledge_test?gssencmode=disable}"
export DATABASE_URL="${DATABASE_URL:-${TEST_DATABASE_URL}}"

if [[ "${QUIET}" -eq 1 ]]; then
  PYTEST_EXTRA+=(-q)
fi

run_pytest() {
  echo ">> pytest"
  # ${arr[@]+…} guards the empty-array case under `set -u` on bash 3.2 (macOS).
  "${PY}" -m pytest ${PYTEST_EXTRA[@]+"${PYTEST_EXTRA[@]}"} "$@"
}

run_alembic_drift() {
  echo ">> alembic upgrade head + drift check (DATABASE_URL)"
  "${PY}" -m alembic upgrade head
  "${PY}" -m alembic check
}

run_eval() {
  local report_dir="${KNOWLEDGE_EVAL_REPORT_DIR:-.eval}"
  echo ">> retrieval eval Q01–Q12 (provider=${KNOWLEDGE_EVAL_PROVIDER:-offline}, report=${report_dir})"
  # `-m eval` overrides the default `-m 'not eval'` from pyproject addopts.
  "${PY}" -m pytest -m eval ${PYTEST_EXTRA[@]+"${PYTEST_EXTRA[@]}"} tests/eval
  if [[ -f "${report_dir}/retrieval_report.md" ]]; then
    cat "${report_dir}/retrieval_report.md"
  fi
}

run_ontology_eval() {
  local report_dir="${KNOWLEDGE_EVAL_REPORT_DIR:-.eval}"
  echo ">> ontology public proxy eval (report=${report_dir})"
  "${PY}" -m pytest -m ontology_eval ${PYTEST_EXTRA[@]+"${PYTEST_EXTRA[@]}"} \
    tests/eval/test_ontology_public_eval.py \
    tests/eval/test_ontology_planner_eval.py \
    tests/eval/test_ontology_entity_resolution_eval.py \
    tests/eval/test_ontology_identifier_coverage_eval.py
  if [[ -f "${report_dir}/ontology_public_pilot.md" ]]; then
    cat "${report_dir}/ontology_public_pilot.md"
  fi
  if [[ -f "${report_dir}/ontology_planner_challenge.md" ]]; then
    cat "${report_dir}/ontology_planner_challenge.md"
  fi
  if [[ -f "${report_dir}/ontology_entity_resolution.md" ]]; then
    cat "${report_dir}/ontology_entity_resolution.md"
  fi
  if [[ -f "${report_dir}/ontology_identifier_coverage.md" ]]; then
    cat "${report_dir}/ontology_identifier_coverage.md"
  fi
}

case "${SUITE}" in
  unit)
    run_pytest
    ;;
  smoke)
    run_pytest tests/test_settings_guard.py tests/test_openapi_contract.py
    ;;
  eval)
    run_eval
    ;;
  ontology-eval)
    run_ontology_eval
    ;;
  integration|all)
    run_alembic_drift
    run_pytest
    ;;
  *)
    echo "unknown suite: ${SUITE}" >&2
    usage >&2
    exit 2
    ;;
esac

echo "OK: suite=${SUITE}"
