from __future__ import annotations

import hashlib

from eth_account import Account
from fastapi.testclient import TestClient

from knowledge.main import app
from knowledge.workers.runner import Worker
from tests.helpers import configure_warehouse_credentials
from tests.test_agent_runs import create_principal, login

CSV = b"region,amount\neast,42\nwest,18\n"


def _setup(client: TestClient, service_id: str) -> tuple[dict[str, str], str]:
    owner_headers = login(client, Account.create())
    configure_warehouse_credentials(client, owner_headers)
    _, api_key = create_principal(client, owner_headers, service_id)
    upload = client.post(
        "/warehouse/upload",
        headers=owner_headers,
        data={"target_dir": "/apps/knowledge.yeying.pub/uploads"},
        files={"file": ("sales.csv", CSV, "text/csv")},
    )
    upload.raise_for_status()
    return {"X-Service-Api-Key": api_key}, upload.json()["warehouse_path"]


def _create_run(client: TestClient, headers: dict[str, str], path: str, *, sha256: str = "", external_id: str) -> dict:
    created = client.post(
        "/service/runs",
        headers=headers,
        json={
            "session_id": "chat-session-retry",
            "external_id": external_id,
            "run_type": "spreadsheet_analysis",
            "inputs": [{"kind": "warehouse_asset", "warehousePath": path, "sha256": sha256, "contentType": "text/csv"}],
            "intent": "按地区汇总金额",
            "constraints": {"analysis_plan": {"group_by": ["region"], "aggregations": [{"column": "amount", "op": "sum", "alias": "total"}]}},
        },
    )
    created.raise_for_status()
    return created.json()


def _events(client: TestClient, headers: dict[str, str], run_id: str) -> list[str]:
    return [event["event_type"] for event in client.get(f"/service/runs/{run_id}/events", headers=headers).json()]


def test_retry_of_cancelled_run_queues_new_attempt_and_leaves_original_untouched():
    with TestClient(app) as client:
        headers, path = _setup(client, "chat-retry-cancelled")
        original = _create_run(client, headers, path, external_id="retry-1")
        cancelled = client.post(f"/service/runs/{original['id']}/cancel", headers=headers, json={})
        assert cancelled.json()["status"] == "cancelled"
        original_events = _events(client, headers, original["id"])

        retried = client.post(f"/service/runs/{original['id']}/retry", headers=headers)
        assert retried.status_code == 200
        child = retried.json()
        assert child["id"] != original["id"]
        assert child["status"] == "queued"
        assert child["attempt"] == 2
        assert child["retry_of_run_id"] == original["id"]
        assert child["external_id"] is None
        assert child["metadata_json"]["intent"] == "按地区汇总金额"
        assert child["warehouse_run_path"].endswith(child["id"])
        child_inputs = client.get(f"/service/runs/{child['id']}/inputs", headers=headers).json()
        assert [item["warehouse_path"] for item in child_inputs] == [path]

        # Idempotent: retrying the same run again returns the same child.
        again = client.post(f"/service/runs/{original['id']}/retry", headers=headers)
        assert again.json()["id"] == child["id"]

        # The original run is not rewritten.
        unchanged = client.get(f"/service/runs/{original['id']}", headers=headers).json()
        assert unchanged["status"] == "cancelled"
        assert unchanged["attempt"] == 1 and unchanged["retry_of_run_id"] is None
        assert _events(client, headers, original["id"]) == original_events

        # The worker claims and completes the retry.
        assert Worker().process_once() == 1
        done = client.get(f"/service/runs/{child['id']}", headers=headers).json()
        assert done["status"] == "completed"
        assert client.get(f"/service/runs/{child['id']}/artifacts", headers=headers).json()

        # A completed attempt cannot be retried.
        conflict = client.post(f"/service/runs/{child['id']}/retry", headers=headers)
        assert conflict.status_code == 409


def test_retry_reuses_frozen_inputs_so_a_changed_file_is_detected():
    with TestClient(app) as client:
        headers, path = _setup(client, "chat-retry-failed")
        wrong_sha = hashlib.sha256(b"a different file version").hexdigest()
        original = _create_run(client, headers, path, sha256=wrong_sha, external_id="retry-2")
        assert Worker().process_once() == 1
        assert client.get(f"/service/runs/{original['id']}", headers=headers).json()["status"] == "failed"

        child = client.post(f"/service/runs/{original['id']}/retry", headers=headers).json()
        child_inputs = client.get(f"/service/runs/{child['id']}/inputs", headers=headers).json()
        assert child_inputs[0]["sha256"] == wrong_sha
        assert Worker().process_once() == 1
        failed_again = client.get(f"/service/runs/{child['id']}", headers=headers).json()
        assert failed_again["status"] == "failed"
        assert failed_again["attempt"] == 2

        # Retrying the newest attempt continues the chain.
        third = client.post(f"/service/runs/{child['id']}/retry", headers=headers).json()
        assert third["attempt"] == 3 and third["retry_of_run_id"] == child["id"]
        # The worker queue is global across tests: never leave a queued run behind.
        client.post(f"/service/runs/{third['id']}/cancel", headers=headers, json={})


def test_retry_rejects_active_non_spreadsheet_and_foreign_runs():
    with TestClient(app) as client:
        headers, path = _setup(client, "chat-retry-guards")
        queued = _create_run(client, headers, path, external_id="retry-3")
        assert client.post(f"/service/runs/{queued['id']}/retry", headers=headers).status_code == 409

        research = client.post("/service/runs", headers=headers, json={"external_id": "retry-4", "run_type": "research"}).json()
        client.post(f"/service/runs/{research['id']}/fail", headers=headers, json={"error_summary": "x"})
        assert client.post(f"/service/runs/{research['id']}/retry", headers=headers).status_code == 400

        client.post(f"/service/runs/{queued['id']}/cancel", headers=headers, json={})
        other_headers, _ = _setup(client, "chat-retry-other")
        assert client.post(f"/service/runs/{queued['id']}/retry", headers=other_headers).status_code == 404
        assert client.post("/service/runs/run_missing/retry", headers=headers).status_code == 404
