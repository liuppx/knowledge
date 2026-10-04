#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-status}"
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-$root_dir/.venv/bin/python}"
api_host="${KNOWLEDGE_HOST:-127.0.0.1}"
api_port="${KNOWLEDGE_PORT:-8000}"
log_dir="${KNOWLEDGE_LOG_DIR:-$root_dir/logs}"
run_dir="${KNOWLEDGE_RUN_DIR:-$root_dir/run}"
api_pid_file="$run_dir/knowledge-api.pid"
worker_pid_file="$run_dir/knowledge-worker.pid"

ensure_dirs() { mkdir -p "$log_dir" "$run_dir"; }

pid_running() {
  local file="$1" pid
  [[ -f "$file" ]] || return 1
  pid="$(cat "$file")"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

start_api() {
  if pid_running "$api_pid_file"; then echo "Knowledge API already running (pid $(cat "$api_pid_file"))."; return; fi
  [[ -x "$python_bin" ]] || { echo "Python not found: $python_bin" >&2; exit 1; }
  cd "$root_dir"
  nohup env PYTHONUNBUFFERED=1 "$python_bin" -m uvicorn knowledge.main:app --host "$api_host" --port "$api_port" \
    >>"$log_dir/api.log" 2>&1 &
  echo $! >"$api_pid_file"
  echo "Knowledge API started (pid $(cat "$api_pid_file"), http://$api_host:$api_port)."
}

start_worker() {
  if pid_running "$worker_pid_file"; then echo "Knowledge worker already running (pid $(cat "$worker_pid_file"))."; return; fi
  [[ -x "$root_dir/scripts/run_worker.sh" ]] || { echo "Worker launcher not found." >&2; exit 1; }
  cd "$root_dir"
  nohup "$root_dir/scripts/run_worker.sh" 1 >>"$log_dir/worker.log" 2>&1 &
  echo $! >"$worker_pid_file"
  echo "Knowledge worker started (pid $(cat "$worker_pid_file"))."
}

stop_one() {
  local label="$1" file="$2"
  if ! pid_running "$file"; then rm -f "$file"; echo "$label not running."; return; fi
  local pid; pid="$(cat "$file")"; kill "$pid" 2>/dev/null || true
  for _ in {1..50}; do pid_running "$file" || break; sleep 0.2; done
  if pid_running "$file"; then kill -9 "$pid" 2>/dev/null || true; fi
  rm -f "$file"; echo "$label stopped."
}

status() {
  if pid_running "$api_pid_file"; then echo "api: running (pid $(cat "$api_pid_file"))"; else echo "api: stopped"; fi
  if pid_running "$worker_pid_file"; then echo "worker: running (pid $(cat "$worker_pid_file"))"; else echo "worker: stopped"; fi
}

ensure_dirs
case "$cmd" in
  start) start_api; start_worker ;;
  start-api) start_api ;;
  start-worker) start_worker ;;
  stop) stop_one "Knowledge worker" "$worker_pid_file"; stop_one "Knowledge API" "$api_pid_file" ;;
  stop-api) stop_one "Knowledge API" "$api_pid_file" ;;
  stop-worker) stop_one "Knowledge worker" "$worker_pid_file" ;;
  restart) stop_one "Knowledge worker" "$worker_pid_file"; stop_one "Knowledge API" "$api_pid_file"; start_api; start_worker ;;
  status) status ;;
  *) echo "Usage: $(basename "$0") {start|stop|restart|status|start-api|start-worker|stop-api|stop-worker}" >&2; exit 1 ;;
esac
