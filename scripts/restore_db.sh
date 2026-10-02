#!/usr/bin/env bash
# Restore a dump produced by scripts/backup_db.sh into the target database.
#
#   scripts/restore_db.sh backups/knowledge-20261001T120000Z.dump
#   RESTORE_VIA_COMPOSE=1 scripts/restore_db.sh backups/...dump
#
# The restore REPLACES existing objects (--clean --if-exists). Stop the API and
# workers first. Afterwards run `alembic upgrade head` (or just start the API,
# which migrates on boot) and rebuild the Weaviate accelerator per KB with
# POST /kbs/{kb_id}/reindex-units. See docs/备份与恢复手册.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DUMP_FILE="${1:?usage: restore_db.sh <dump-file>}"
[[ -f "${DUMP_FILE}" ]] || { echo "dump not found: ${DUMP_FILE}" >&2; exit 1; }

if [[ -z "${DATABASE_URL:-}" && -f "${ROOT_DIR}/.env" ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "${ROOT_DIR}/.env" | tail -1 | cut -d= -f2-)"
fi

if [[ "${RESTORE_CONFIRM:-}" != "yes" ]]; then
  echo "This will overwrite the target database. Re-run with RESTORE_CONFIRM=yes." >&2
  exit 2
fi

if [[ "${RESTORE_VIA_COMPOSE:-0}" == "1" ]]; then
  docker compose -f "${ROOT_DIR}/compose.yaml" exec -T postgres \
    pg_restore --clean --if-exists --no-owner --no-privileges -U knowledge -d knowledge < "${DUMP_FILE}"
else
  : "${DATABASE_URL:?DATABASE_URL is required (or set RESTORE_VIA_COMPOSE=1)}"
  pg_restore --clean --if-exists --no-owner --no-privileges --dbname="${DATABASE_URL}" "${DUMP_FILE}"
fi

echo "restore complete. Next: start the API (migrations run on boot) and reindex units per KB."
