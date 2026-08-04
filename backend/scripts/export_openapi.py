from __future__ import annotations

from pathlib import Path
import sys

import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from knowledge.main import app  # noqa: E402


def main() -> None:
    schema = app.openapi()
    schema.setdefault("info", {})["description"] = "knowledge 控制面、知识生产、发布、检索与 Agent Run API。"
    schema["info"]["version"] = "1.0.0"
    schema.setdefault(
        "servers",
        [{"url": "http://127.0.0.1:8000", "description": "本地开发环境"}],
    )
    output = REPO_ROOT / "docs" / "openapi" / "knowledge.openapi.yaml"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(schema, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(
        f"wrote {output.relative_to(REPO_ROOT)} "
        f"({len(schema.get('paths', {}))} paths, "
        f"{len(schema.get('components', {}).get('schemas', {}))} schemas)"
    )


if __name__ == "__main__":
    main()
