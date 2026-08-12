from datetime import datetime, timezone

from knowledge.services.warehouse import S3WarehouseGateway, WarehouseRequestAuth


class _ObjectBody:
    def read(self) -> bytes:
        return b"spreadsheet"


class _S3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict] = []

    def list_objects_v2(self, **kwargs):
        assert kwargs == {"Bucket": "apps", "Prefix": "knowledge.yeying.pub/uploads/", "Delimiter": "/"}
        return {
            "CommonPrefixes": [{"Prefix": "knowledge.yeying.pub/uploads/archive/"}],
            "Contents": [{"Key": "knowledge.yeying.pub/uploads/sales.csv", "Size": 42, "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)}],
        }

    def put_object(self, **kwargs) -> None:
        self.put_calls.append(kwargs)

    def get_object(self, **kwargs):
        assert kwargs == {"Bucket": "apps", "Key": "knowledge.yeying.pub/uploads/sales.csv"}
        return {"Body": _ObjectBody()}


def test_s3_gateway_maps_warehouse_paths_to_bucket_and_key() -> None:
    client = _S3Client()
    gateway = S3WarehouseGateway("http://warehouse.example.test:6066", "us-east-1")
    gateway._client = lambda auth: client  # type: ignore[method-assign]
    auth = WarehouseRequestAuth.basic("AKexample", "warehouse-s3-secret")

    entries = gateway.browse("0xowner", "/apps/knowledge.yeying.pub/uploads", auth)
    assert [(item.path, item.entry_type) for item in entries] == [
        ("/apps/knowledge.yeying.pub/uploads/archive", "directory"),
        ("/apps/knowledge.yeying.pub/uploads/sales.csv", "file"),
    ]
    assert gateway.read_file("0xowner", "/apps/knowledge.yeying.pub/uploads/sales.csv", auth) == b"spreadsheet"
    assert gateway.upload_file("0xowner", "/apps/knowledge.yeying.pub/uploads", "result.csv", b"result", auth) == "/apps/knowledge.yeying.pub/uploads/result.csv"
    assert client.put_calls == [{"Bucket": "apps", "Key": "knowledge.yeying.pub/uploads/result.csv", "Body": b"result"}]
