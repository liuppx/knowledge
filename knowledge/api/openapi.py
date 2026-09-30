from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "docs" / "openapi" / "knowledge.openapi.yaml"

# Bump when the published contract changes in a breaking way. Consumers
# (Chat / Agent / Project) pin against this version.
OPENAPI_VERSION = "1.0.0"
OPENAPI_DESCRIPTION = "knowledge 控制面、知识生产、发布、检索与 Agent Run API。"
DEFAULT_SERVERS = [{"url": "http://127.0.0.1:8000", "description": "本地开发环境"}]


def build_openapi_schema() -> dict:
    """Return the OpenAPI schema with the published info/servers metadata applied.

    Shared by the export script and the contract test so the generated document
    and the drift check are always produced the same way.
    """
    # Imported lazily so importing this module does not build the whole app
    # unless a schema is actually requested.
    from knowledge.main import app

    schema = app.openapi()
    schema.setdefault("info", {})["description"] = OPENAPI_DESCRIPTION
    schema["info"]["version"] = OPENAPI_VERSION
    schema.setdefault("servers", DEFAULT_SERVERS)
    return schema


def dump_openapi_yaml(schema: dict | None = None) -> str:
    """Serialize the schema to the canonical YAML representation."""
    if schema is None:
        schema = build_openapi_schema()
    return yaml.safe_dump(schema, allow_unicode=True, sort_keys=False, width=120)


def write_openapi_spec() -> tuple[int, int]:
    """Write the spec to SPEC_PATH. Returns (path_count, schema_count)."""
    schema = build_openapi_schema()
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(dump_openapi_yaml(schema), encoding="utf-8")
    return (
        len(schema.get("paths", {})),
        len(schema.get("components", {}).get("schemas", {})),
    )
