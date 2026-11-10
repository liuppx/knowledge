from __future__ import annotations

import base64
import hashlib
import json

import httpx
import pytest

from knowledge.adapters.warehouse_tool import WarehouseToolAssetStore, WarehouseToolAuthorization
from knowledge.ports.storage import AssetAccessContext, AssetStoreError


def make_store(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    store = WarehouseToolAssetStore("https://warehouse.example.test/", client=client)
    context = AssetAccessContext(
        owner_id="wallet-owner",
        authorization=WarehouseToolAuthorization("short-lived-tool-secret"),
        credential_root="/apps/knowledge",
        trace_id="run-123:step-2",
    )
    return store, context


def test_tool_adapter_uses_published_call_contract_and_maps_metadata():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "name": "warehouse.object.stat",
                "requestId": "req-1",
                "traceId": "run-123:step-2",
                "result": {
                    "path": "/apps/knowledge/input.csv",
                    "size": 17,
                    "etag": "e1",
                    "checksumSha256": "a" * 64,
                    "contentType": "text/csv",
                    "modifiedAt": "2026-11-08T10:00:00Z",
                },
            },
        )

    store, context = make_store(handler)
    ref = store.stat(context, "/apps/knowledge/input.csv")

    assert seen[0].url.path == "/api/v1/public/tools/warehouse/call"
    assert seen[0].headers["Authorization"] == "Bearer short-lived-tool-secret"
    body = json.loads(seen[0].content)
    assert body == {
        "name": "warehouse.object.stat",
        "arguments": {"path": "/apps/knowledge/input.csv"},
        "traceId": "run-123:step-2",
    }
    assert ref.object_id == "/apps/knowledge/input.csv"
    assert ref.etag == "e1"
    assert ref.sha256 == "a" * 64
    assert ref.modified_at is not None


def test_tool_adapter_decodes_and_verifies_binary_content():
    content = b"\x00warehouse-binary"
    checksum = hashlib.sha256(content).hexdigest()

    def handler(request):
        body = json.loads(request.content)
        assert body["name"] == "warehouse.object.read"
        assert body["arguments"]["maxBytes"] == 5 * 1024 * 1024
        return httpx.Response(
            200,
            json={
                "name": "warehouse.object.read",
                "result": {
                    "metadata": {"path": "/apps/knowledge/a.bin", "checksumSha256": checksum},
                    "mode": "content",
                    "encoding": "base64",
                    "content": base64.b64encode(content).decode("ascii"),
                    "truncated": False,
                },
            },
        )

    store, context = make_store(handler)
    assert store.read(context, "/apps/knowledge/a.bin") == content


def test_tool_adapter_writes_idempotent_utf8_object_and_returns_reference():
    content = b"manifest"

    def handler(request):
        body = json.loads(request.content)
        assert body["name"] == "warehouse.object.put"
        assert body["arguments"] == {
            "path": "/apps/knowledge/runs/r1/manifest.json",
            "content": "manifest",
            "encoding": "utf-8",
            "contentType": "application/json",
            "checksumSha256": hashlib.sha256(content).hexdigest(),
            "overwrite": True,
            "ifMatch": "etag-old",
        }
        return httpx.Response(
            200,
            json={
                "name": "warehouse.object.put",
                "result": {
                    "path": "/apps/knowledge/runs/r1/manifest.json",
                    "size": len(content),
                    "etag": "etag-new",
                    "checksumSha256": hashlib.sha256(content).hexdigest(),
                    "contentType": "application/json",
                },
            },
        )

    store, context = make_store(handler)
    ref = store.write(
        context,
        "/apps/knowledge/runs/r1",
        "manifest.json",
        content,
        "application/json",
        overwrite=True,
        if_match="etag-old",
    )
    assert ref.object_id.endswith("manifest.json")
    assert ref.etag == "etag-new"
    assert ref.size == len(content)


def test_tool_adapter_maps_contract_errors_without_echoing_upstream_message():
    def handler(request):
        return httpx.Response(409, json={"code": "OBJECT_EXISTS", "message": "sensitive upstream detail"})

    store, context = make_store(handler)
    with pytest.raises(AssetStoreError) as raised:
        store.stat(context, "/apps/knowledge/a")
    assert raised.value.code == "conflict"
    assert "sensitive" not in str(raised.value)


def test_tool_adapter_refuses_content_over_five_mib():
    store, context = make_store(lambda request: httpx.Response(500))
    with pytest.raises(AssetStoreError) as raised:
        store.write(context, "/apps/knowledge", "large.bin", b"x" * (5 * 1024 * 1024 + 1))
    assert raised.value.code == "too_large"


def test_tool_adapter_rejects_truncated_read_results():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "name": "warehouse.object.read",
                "result": {
                    "metadata": {"path": "/apps/knowledge/large.csv"},
                    "mode": "content",
                    "encoding": "utf-8",
                    "content": "partial",
                    "truncated": True,
                },
            },
        )

    store, context = make_store(handler)
    with pytest.raises(AssetStoreError) as raised:
        store.read(context, "/apps/knowledge/large.csv")
    assert raised.value.code == "too_large"
