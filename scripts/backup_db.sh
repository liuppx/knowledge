#!/usr/bin/env bash
# Dump the Knowledge PostgreSQL database (the source of truth) to backups/.
#
#   scripts/backup_db.sh                 # uses DATABASE_URL from env or .env
#   DATABASE_URL=postgresql://... scripts/backup_db.sh
#   BACKUP_VIA_COMPOSE=1 scripts/backup_db.sh   # run pg_dump inside the compose postgres container
#
# Output: backups/knowledge-<UTC timestamp>.dump (pg_dump custom format, compressed).
# Weaviate is NOT backed up: it is a rebuildable accelerator (see 备份与恢复手册.md).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${BACKUP_DIR:-${ROOT_DIR}/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${OUT_DIR}/knowledge-${STAMP}.dump"

if [[ -z "${DATABASE_URL:-}" && -f "${ROOT_DIR}/.env" ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "${ROOT_DIR}/.env" | tail -1 | cut -d= -f2-)"
fi
mkdir -p "${OUT_DIR}"

if [[ "${BACKUP_VIA_COMPOSE:-0}" == "1" ]]; then
  docker compose -f "${ROOT_DIR}/compose.yaml" exec -T postgres \
    pg_dump --format=custom --no-owner --no-privileges -U knowledge knowledge > "${OUT_FILE}"
else
  : "${DATABASE_URL:?DATABASE_URL is required (or set BACKUP_VIA_COMPOSE=1)}"
  pg_dump --format=custom --no-owner --no-privileges --dbname="${DATABASE_URL}" --file="${OUT_FILE}"
fi

SIZE="$(du -h "${OUT_FILE}" | cut -f1)"
echo "backup written: ${OUT_FILE} (${SIZE})"
