from __future__ import annotations

import pytest

from knowledge.api.openapi import SPEC_PATH, dump_openapi_yaml, build_openapi_schema


# The consumer-facing runtime contract used by Chat / Agent / Project. These
# paths and methods are frozen: removing or renaming any of them is a breaking
# change and must go through an OPENAPI_VERSION bump and consumer coordination.
FROZEN_SERVICE_SURFACE: dict[str, set[str]] = {
    "/service/search": {"post"},
    "/service/search/formal": {"post"},
    "/service/search/evidence": {"post"},
    "/service/kbs": {"get"},
    "/service/grants": {"get"},
    "/service/releases/current": {"get"},
    "/service/runs": {"post"},
    "/service/runs/{run_id}": {"get"},
    "/service/runs/{run_id}/inputs": {"get"},
    "/service/runs/{run_id}/steps": {"get"},
    "/service/runs/{run_id}/events": {"get"},
    "/service/runs/{run_id}/artifacts": {"get", "post"},
    "/service/runs/{run_id}/context": {"put"},
    "/service/runs/{run_id}/complete": {"post"},
    "/service/runs/{run_id}/fail": {"post"},
    "/service/runs/{run_id}/cancel": {"post"},
}


def test_committed_openapi_is_current() -> None:
    """The committed spec must match what the app generates.

    Freezes the published contract: any endpoint or schema change is only
    accepted once `python scripts/export_openapi.py` is re-run and the result
    committed, making contract changes explicit and reviewable.
    """
    generated = dump_openapi_yaml()
    committed = SPEC_PATH.read_text(encoding="utf-8")
    assert generated == committed, (
        "docs/openapi/knowledge.openapi.yaml is out of date. "
        "Run `python scripts/export_openapi.py` and commit the result."
    )


@pytest.mark.parametrize("path, methods", sorted(FROZEN_SERVICE_SURFACE.items()))
def test_service_contract_surface_present(path: str, methods: set[str]) -> None:
    """Every frozen consumer endpoint must exist with its expected methods."""
    schema = build_openapi_schema()
    paths = schema.get("paths", {})
    assert path in paths, f"missing frozen service endpoint: {path}"
    present = {method.lower() for method in paths[path]} & {"get", "post", "put", "patch", "delete"}
    missing = methods - present
    assert not missing, f"{path} is missing frozen methods: {sorted(missing)}"
