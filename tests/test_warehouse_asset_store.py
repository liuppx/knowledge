from __future__ import annotations

import hashlib

import httpx
import pytest

from knowledge.adapters.warehouse_assets import LegacyWarehouseAssetStore
from knowledge.ports.storage import AssetAccessContext, AssetStoreError
from knowledge.services.warehouse import WarehouseRequestAuth


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.content = b"stored input"

    def ensure_app_space(self, owner, auth=None, *, base_path=None, target_path=None):
        self.calls.append(("ensure", owner, auth, base_path, target_path))

    def upload_file(self, owner, target_dir, file_name, content, auth=None, content_type=None):
        self.calls.append(("put", owner, target_dir, file_name, content, auth, content_type))
        return f"{target_dir.rstrip('/')}/{file_name}"

    def read_file(self, owner, path, auth=None):
        self.calls.append(("get", owner, path, auth))
        return self.content


def test_legacy_warehouse_adapter_returns_provider_neutral_reference():
    gateway = RecordingGateway()
    store = LegacyWarehouseAssetStore(gateway)
    auth = WarehouseRequestAuth.basic("ak_test", "sk_test")
    context = AssetAccessContext("0xowner", auth, "/apps/knowledge")
    content = b"report"

    reference = store.write(context, "/apps/knowledge/runs/run-1/artifacts", "../report.md", content, "text/markdown")

    assert reference.provider == "warehouse"
    assert reference.object_id.endswith("/artifacts/report.md")
    assert reference.sha256 == hashlib.sha256(content).hexdigest()
    assert reference.size == len(content)
    assert reference.content_type == "text/markdown"
    assert gateway.calls[0] == (
        "ensure", "0xowner", auth, "/apps/knowledge", "/apps/knowledge/runs/run-1/artifacts"
    )
    assert gateway.calls[1][-3:] == (content, auth, "text/markdown")


def test_legacy_warehouse_adapter_reads_using_resolved_context():
    gateway = RecordingGateway()
    store = LegacyWarehouseAssetStore(gateway)
    auth = WarehouseRequestAuth.basic("ak_test", "sk_test")
    context = AssetAccessContext("0xowner", auth, "/apps/knowledge")

    content = store.read(context, "/apps/knowledge/uploads/source.csv")

    assert content == b"stored input"
    assert gateway.calls == [("get", "0xowner", "/apps/knowledge/uploads/source.csv", auth)]


def test_legacy_adapter_rejects_conditional_write_it_cannot_enforce():
    store = LegacyWarehouseAssetStore(RecordingGateway())
    context = AssetAccessContext("0xowner", WarehouseRequestAuth.basic("ak_test", "sk_test"), "/apps/knowledge")

    with pytest.raises(AssetStoreError) as raised:
        store.write(context, "/apps/knowledge/runs/r1", "manifest.json", b"{}", if_match="etag-old")

    assert raised.value.code == "invalid_request"


@pytest.mark.parametrize(
    ("status", "code"),
    [(403, "permission_denied"), (404, "not_found"), (412, "version_conflict"), (503, "unavailable")],
)
def test_legacy_warehouse_adapter_maps_transport_errors_to_stable_codes(status, code):
    request = httpx.Request("GET", "https://warehouse.example/object")
    response = httpx.Response(status, request=request)
    error = LegacyWarehouseAssetStore._translate(httpx.HTTPStatusError("upstream failure", request=request, response=response))

    assert isinstance(error, AssetStoreError)
    assert error.code == code
