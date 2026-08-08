from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


@dataclass
class CheckResult:
    check: str
    status: str
    duration_ms: int
    detail: str
    observed: dict[str, Any]


class WarehouseContractProbe:
    def __init__(self, base_url: str, headers: dict[str, str], timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.client = httpx.Client(timeout=timeout, follow_redirects=False)
        self.results: list[CheckResult] = []

    def close(self) -> None:
        self.client.close()

    def metadata(self, path: str) -> dict[str, Any] | None:
        started = time.monotonic()
        try:
            response = self.client.get(
                f"{self.base_url}/api/v1/public/assets/object?path={quote(path, safe='')}",
                headers=self.headers,
            )
            payload = self._json(response)
            response.raise_for_status()
            required = {"path", "size", "etag", "contentType", "modifiedAt"}
            missing = sorted(required - set(payload))
            status = "pass" if not missing else "fail"
            detail = "metadata fields are present" if not missing else f"missing fields: {', '.join(missing)}"
            self._record("WH-P0-01 metadata identity", status, started, detail, payload)
            return payload
        except Exception as exc:  # noqa: BLE001 - probe must record remote failures
            self._record("WH-P0-01 metadata identity", "fail", started, str(exc), {})
            return None

    def head(self, path: str, expected: dict[str, Any] | None) -> None:
        started = time.monotonic()
        try:
            response = self.client.head(self._content_url(path), headers=self.headers)
            response.raise_for_status()
            observed = self._identity_headers(response)
            missing = [name for name in ("etag", "content_length", "last_modified") if not observed.get(name)]
            if expected and expected.get("size") is not None and observed.get("content_length"):
                if int(observed["content_length"]) != int(expected["size"]):
                    missing.append("content_length_mismatch")
            self._record(
                "WH-P0-02 low-cost HEAD",
                "pass" if not missing else "fail",
                started,
                "HEAD identity is present" if not missing else f"problems: {', '.join(missing)}",
                observed,
            )
        except Exception as exc:  # noqa: BLE001
            self._record("WH-P0-02 low-cost HEAD", "fail", started, str(exc), {})

    def range_read(self, path: str) -> None:
        started = time.monotonic()
        try:
            response = self.client.get(self._content_url(path), headers={**self.headers, "Range": "bytes=0-63"})
            observed = {
                "status_code": response.status_code,
                "content_range": response.headers.get("content-range", ""),
                "accept_ranges": response.headers.get("accept-ranges", ""),
                "bytes_received": len(response.content),
            }
            passed = response.status_code == 206 and bool(observed["content_range"]) and len(response.content) <= 64
            self._record(
                "WH-P0-03 range read",
                "pass" if passed else "fail",
                started,
                "server returned a bounded partial response" if passed else "expected 206 with Content-Range and at most 64 bytes",
                observed,
            )
        except Exception as exc:  # noqa: BLE001
            self._record("WH-P0-03 range read", "fail", started, str(exc), {})

    def conditional_read(self, path: str, etag: str | None) -> None:
        if not etag:
            self._record_now("WH-P0-03 If-Match", "skip", "metadata did not provide an ETag", {})
            return
        started = time.monotonic()
        invalid_etag = '"knowledge-contract-probe-invalid-etag"'
        try:
            response = self.client.get(self._content_url(path), headers={**self.headers, "If-Match": invalid_etag, "Range": "bytes=0-0"})
            observed = {"status_code": response.status_code, "etag": response.headers.get("etag", "")}
            passed = response.status_code == 412
            self._record(
                "WH-P0-03 If-Match",
                "pass" if passed else "fail",
                started,
                "stale identity was rejected" if passed else "expected 412 for a deliberately stale ETag",
                observed,
            )
        except Exception as exc:  # noqa: BLE001
            self._record("WH-P0-03 If-Match", "fail", started, str(exc), {})

    def checksum(self, path: str, metadata: dict[str, Any] | None) -> None:
        started = time.monotonic()
        try:
            response = self.client.get(self._content_url(path), headers=self.headers)
            response.raise_for_status()
            actual = hashlib.sha256(response.content).hexdigest()
            declared = str((metadata or {}).get("checksumSha256") or response.headers.get("x-warehouse-checksum-sha256") or "")
            observed = {"declared_sha256": declared, "actual_sha256": actual, "bytes_received": len(response.content)}
            passed = bool(declared) and declared.lower() == actual
            self._record(
                "WH-P0-01 checksum identity",
                "pass" if passed else "fail",
                started,
                "declared checksum matches content" if passed else "checksum is absent or does not match downloaded content",
                observed,
            )
        except Exception as exc:  # noqa: BLE001
            self._record("WH-P0-01 checksum identity", "fail", started, str(exc), {})

    def write(self, path: str) -> None:
        content = b"knowledge warehouse contract probe\n"
        sha256 = hashlib.sha256(content).hexdigest()
        idempotency_key = f"knowledge-contract-{sha256[:16]}"
        started = time.monotonic()
        try:
            response = self.client.put(
                self._content_url(path),
                headers={
                    **self.headers,
                    "Content-Type": "text/plain",
                    "X-Warehouse-Checksum-SHA256": sha256,
                    "Idempotency-Key": idempotency_key,
                },
                content=content,
            )
            payload = self._json(response)
            response.raise_for_status()
            observed = {
                "status_code": response.status_code,
                "path": payload.get("path"),
                "etag": payload.get("etag"),
                "checksumSha256": payload.get("checksumSha256"),
                "idempotency_key": idempotency_key,
            }
            passed = payload.get("checksumSha256") == sha256
            self._record(
                "WH-P0-04 checked write",
                "pass" if passed else "fail",
                started,
                "write returned the expected checksum" if passed else "write did not return the expected checksum",
                observed,
            )
        except Exception as exc:  # noqa: BLE001
            self._record("WH-P0-04 checked write", "fail", started, str(exc), {})

    def report(self, asset_path: str, write_path: str | None) -> dict[str, Any]:
        statuses = {status: sum(item.status == status for item in self.results) for status in ("pass", "fail", "skip")}
        return {
            "schema": "knowledge.warehouse-contract-probe.v1",
            "warehouseBaseUrl": self.base_url,
            "assetPath": asset_path,
            "writePath": write_path,
            "summary": statuses,
            "checks": [asdict(item) for item in self.results],
        }

    def _content_url(self, path: str) -> str:
        return f"{self.base_url}/api/v1/public/assets/object/content?path={quote(path, safe='')}"

    @staticmethod
    def _identity_headers(response: httpx.Response) -> dict[str, Any]:
        return {
            "status_code": response.status_code,
            "etag": response.headers.get("etag", ""),
            "checksum_sha256": response.headers.get("x-warehouse-checksum-sha256", ""),
            "content_length": response.headers.get("content-length", ""),
            "last_modified": response.headers.get("last-modified", ""),
            "request_id": response.headers.get("x-request-id", ""),
        }

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {"status_code": response.status_code, "body": response.text[:500]}
        return payload if isinstance(payload, dict) else {"value": payload}

    def _record(self, check: str, status: str, started: float, detail: str, observed: dict[str, Any]) -> None:
        self.results.append(CheckResult(check, status, int((time.monotonic() - started) * 1000), detail, observed))

    def _record_now(self, check: str, status: str, detail: str, observed: dict[str, Any]) -> None:
        self.results.append(CheckResult(check, status, 0, detail, observed))


def auth_headers(args: argparse.Namespace) -> dict[str, str]:
    if args.bearer_token:
        return {"Authorization": f"Bearer {args.bearer_token}"}
    if args.username:
        raw = f"{args.username}:{args.password or ''}".encode("utf-8")
        return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}
    raise SystemExit("provide --bearer-token or --username/--password")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the Warehouse object contract required by Knowledge V2.")
    parser.add_argument("--base-url", required=True, help="Warehouse origin, for example http://127.0.0.1:6065")
    parser.add_argument("--asset-path", required=True, help="Existing readable object used by read-only checks")
    parser.add_argument("--write-path", help="Optional disposable object path used by the checked PUT test")
    parser.add_argument("--bearer-token")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-full-checksum", action="store_true", help="Do not download the complete object")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    probe = WarehouseContractProbe(args.base_url, auth_headers(args), args.timeout)
    try:
        metadata = probe.metadata(args.asset_path)
        probe.head(args.asset_path, metadata)
        probe.range_read(args.asset_path)
        probe.conditional_read(args.asset_path, str((metadata or {}).get("etag") or ""))
        if args.skip_full_checksum:
            probe._record_now("WH-P0-01 checksum identity", "skip", "disabled by --skip-full-checksum", {})
        else:
            probe.checksum(args.asset_path, metadata)
        if args.write_path:
            probe.write(args.write_path)
        else:
            probe._record_now("WH-P0-04 checked write", "skip", "no --write-path was provided", {})
        report = probe.report(args.asset_path, args.write_path)
    finally:
        probe.close()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if report["summary"]["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
