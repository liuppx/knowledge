#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
host="${KNOWLEDGE_HOST:-127.0.0.1}"
port="${KNOWLEDGE_PORT:-8002}"
base_url="${HEALTH_BASE_URL:-http://${host}:${port}}"
timeout="${HEALTH_TIMEOUT:-5}"
run_dir="${KNOWLEDGE_RUN_DIR:-${RUN_DIR:-$root_dir/run}}"
level="readiness"

usage() {
  printf 'Usage: %s [--level liveness|readiness|all] [--base-url URL] [--timeout seconds]\n' "$(basename "$0")"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --level) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; level=$2; shift 2 ;;
    --base-url) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; base_url=$2; shift 2 ;;
    --timeout) [[ $# -ge 2 ]] || { usage >&2; exit 2; }; timeout=$2; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ "$level" =~ ^(liveness|readiness|all)$ ]] || { usage >&2; exit 2; }
[[ "$timeout" =~ ^[0-9]+([.][0-9]+)?$ ]] || { printf 'Invalid timeout: %s\n' "$timeout" >&2; exit 2; }
command -v curl >/dev/null 2>&1 || { printf 'curl is required\n' >&2; exit 3; }

check_process() {
  local component pid_file pid
  for component in api worker; do
    pid_file="$run_dir/knowledge-${component}.pid"
    [[ -f "$pid_file" ]] || { printf 'Knowledge %s pid file is missing: %s\n' "$component" "$pid_file" >&2; return 1; }
    pid="$(tr -d '[:space:]' < "$pid_file")"
    [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null || {
      printf 'Knowledge %s process is not running\n' "$component" >&2
      return 1
    }
  done
}

check_http() {
  curl --silent --show-error --fail --max-time "$timeout" "${base_url%/}/health" >/dev/null
}

check_process || exit 1
if [[ "$level" != liveness ]]; then
  check_http || exit 1
fi
printf 'knowledge level=%s status=pass url=%s/health\n' "$level" "${base_url%/}"
