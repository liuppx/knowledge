#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/package-common.sh"
package_common_init knowledge "$@"
for command_name in npm uv; do command -v "$command_name" >/dev/null 2>&1 || package_fail "$command_name is required"; done
(cd "$PACKAGE_ROOT_DIR/web" && npm install --no-audit --no-fund && npm run build)
(cd "$PACKAGE_ROOT_DIR" && uv sync --locked --no-dev --no-install-project)
[[ -f "$PACKAGE_ROOT_DIR/web/dist/index.html" ]] || package_fail 'web build output is missing'
package_make_root knowledge
cp -R "$PACKAGE_ROOT_DIR/.venv" "$PACKAGE_DIR/.venv"
venv_python="$PACKAGE_DIR/.venv/bin/python"
if [[ -L "$venv_python" ]]; then
  resolved_python="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$venv_python")"
  [[ -x "$resolved_python" ]] || package_fail "virtualenv interpreter target is missing: $resolved_python"
  cp -p "$resolved_python" "$venv_python.tmp"
  mv "$venv_python.tmp" "$venv_python"
fi
for python_link in "$PACKAGE_DIR"/.venv/bin/python[0-9]*; do
  [[ -L "$python_link" ]] || continue
  ln -sfn python "$python_link"
done
for directory in knowledge docs migrations config; do [[ ! -d "$PACKAGE_ROOT_DIR/$directory" ]] || cp -R "$PACKAGE_ROOT_DIR/$directory" "$PACKAGE_DIR/$directory"; done
for file in alembic.ini pyproject.toml uv.lock requirements.txt .env.template; do [[ ! -f "$PACKAGE_ROOT_DIR/$file" ]] || cp "$PACKAGE_ROOT_DIR/$file" "$PACKAGE_DIR/"; done
package_copy_scripts "$PACKAGE_DIR/scripts"
package_strip_build_files "$PACKAGE_DIR"
find "$PACKAGE_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
package_finish_artifact service

package_make_root knowledge-web
PACKAGE_HEALTH_PATH=/index.html
cp -R "$PACKAGE_ROOT_DIR/web/dist/." "$PACKAGE_DIR/"
package_finish_artifact static
package_finish
