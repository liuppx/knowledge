#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="${OUTPUT_DIR:-$root_dir/output}"
project_name="${PROJECT_NAME:-knowledge}"
version="${1:-$(git -C "$root_dir" describe --tags --always --dirty)}"
stage_dir="$out_dir/${project_name}-${version}"
archive="$out_dir/${project_name}-${version}.tar.gz"

command -v tar >/dev/null || { echo "tar is required" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm is required to build the frontend" >&2; exit 1; }
[[ -x "$root_dir/.venv/bin/python" ]] || { echo "Create .venv and install requirements first" >&2; exit 1; }

mkdir -p "$out_dir"
echo "Building frontend..."
(cd "$root_dir/web" && npm run build)
rm -rf "$stage_dir" "$archive"
mkdir -p "$stage_dir"
# Mirror the repo layout so the unpacked tree is runnable as-is:
# - knowledge/ + scripts/ + docs/ + web/dist/ stay at the top level
# - web/dist (not dist) so FastAPI's web_dist_dir lookup resolves
# - alembic.ini + migrations/ are required by the lifespan's ensure_database_schema
# - __pycache__ directories are excluded to keep the archive small
cp -R "$root_dir/knowledge" "$root_dir/scripts" "$root_dir/docs" "$root_dir/migrations" "$root_dir/config" "$stage_dir/"
mkdir -p "$stage_dir/web"
cp -R "$root_dir/web/dist" "$stage_dir/web/"
cp "$root_dir/alembic.ini" "$root_dir/pyproject.toml" "$root_dir/requirements.txt" "$root_dir/.env.template" "$stage_dir/"
find "$stage_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
tar -czf "$archive" -C "$out_dir" "$(basename "$stage_dir")"
rm -rf "$stage_dir"
echo "Package created: $archive"
