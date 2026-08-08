from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import httpx


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_warehouse_contract.py"
SPEC = importlib.util.spec_from_file_location("verify_warehouse_contract", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
WarehouseContractProbe = MODULE.WarehouseContractProbe


def test_contract_probe_accepts_identity_range_condition_and_checksum():
    content = b"region,amount\neast,42\n"
    checksum = hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/assets/object"):
            return httpx.Response(
                200,
                json={
                    "path": "/apps/knowledge.yeying.pub/fixture.csv",
                    "size": len(content),
                    "etag": "fixture-etag",
                    "checksumSha256": checksum,
                    "contentType": "text/csv",
                    "modifiedAt": "2026-08-05T00:00:00Z",
                },
            )
        if request.method == "HEAD":
            return httpx.Response(
                200,
                headers={
                    "ETag": '"fixture-etag"',
                    "X-Warehouse-Checksum-SHA256": checksum,
                    "Content-Length": str(len(content)),
                    "Last-Modified": "Wed, 05 Aug 2026 00:00:00 GMT",
                },
            )
        if request.headers.get("if-match"):
            return httpx.Response(412)
        if request.headers.get("range"):
            return httpx.Response(206, content=content[:1], headers={"Content-Range": f"bytes 0-0/{len(content)}"})
        return httpx.Response(200, content=content, headers={"X-Warehouse-Checksum-SHA256": checksum})

    probe = WarehouseContractProbe("https://warehouse.example", {"Authorization": "Bearer test"}, 5)
    probe.client.close()
    probe.client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        metadata = probe.metadata("/apps/knowledge.yeying.pub/fixture.csv")
        probe.head("/apps/knowledge.yeying.pub/fixture.csv", metadata)
        probe.range_read("/apps/knowledge.yeying.pub/fixture.csv")
        probe.conditional_read("/apps/knowledge.yeying.pub/fixture.csv", "fixture-etag")
        probe.checksum("/apps/knowledge.yeying.pub/fixture.csv", metadata)
        report = probe.report("/apps/knowledge.yeying.pub/fixture.csv", None)
    finally:
        probe.close()

    assert report["summary"] == {"pass": 5, "fail": 0, "skip": 0}
    assert report["schema"] == "knowledge.warehouse-contract-probe.v1"


def test_contract_probe_reports_unsupported_range_and_if_match():
    content = b"a,b\n1,2\n"
    checksum = hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/assets/object"):
            return httpx.Response(
                200,
                json={
                    "path": "/fixture.csv",
                    "size": len(content),
                    "etag": "etag",
                    "checksumSha256": checksum,
                    "contentType": "text/csv",
                    "modifiedAt": "2026-08-05T00:00:00Z",
                },
            )
        return httpx.Response(200, content=content)

    probe = WarehouseContractProbe("https://warehouse.example", {}, 5)
    probe.client.close()
    probe.client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        metadata = probe.metadata("/fixture.csv")
        probe.range_read("/fixture.csv")
        probe.conditional_read("/fixture.csv", str(metadata["etag"]))
        report = probe.report("/fixture.csv", None)
    finally:
        probe.close()

    assert report["summary"]["pass"] == 1
    assert report["summary"]["fail"] == 2
    assert {item["check"] for item in report["checks"] if item["status"] == "fail"} == {
        "WH-P0-03 range read",
        "WH-P0-03 If-Match",
    }
