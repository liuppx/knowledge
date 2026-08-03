from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from pathlib import Path
import hashlib
import json

from knowledge.main import app
from knowledge.core.settings import get_settings
from tests.helpers import configure_warehouse_credentials


def login(client: TestClient, account) -> dict[str, str]:
    challenge = client.post("/auth/challenge", json={"wallet_address": account.address}).json()
    signed = account.sign_message(encode_defunct(text=challenge["message"]))
    response = client.post(
        "/auth/verify",
        json={"wallet_address": account.address, "signature": signed.signature.hex()},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_principal(client: TestClient, headers: dict[str, str], service_id: str) -> tuple[dict, str]:
    response = client.post(
        "/service-principals",
        headers=headers,
        json={"service_id": service_id, "display_name": service_id, "identity_type": "api_key"},
    )
    response.raise_for_status()
    payload = response.json()
    return payload["principal"], payload["api_key"]


def test_agent_run_lifecycle_is_idempotent_and_terminal():
    with TestClient(app) as client:
        account = Account.create()
        owner_headers = login(client, account)
        configure_warehouse_credentials(client, owner_headers)
        _, api_key = create_principal(client, owner_headers, "community-chat")
        service_headers = {"X-Service-Api-Key": api_key}
        create_payload = {
            "session_id": "chat-session-1",
            "external_id": "chat-session-1:message-42",
            "run_type": "research",
            "inputs": [{"kind": "warehouse_asset", "warehousePath": "/apps/knowledge.yeying.pub/uploads/source.pdf"}],
            "metadata": {"skill": "research"},
        }
        created = client.post("/service/runs", headers=service_headers, json=create_payload)
        assert created.status_code == 200
        run = created.json()
        assert run["status"] == "running"
        assert run["warehouse_run_path"].endswith(f"/runs/{run['id']}")
        assert run["manifest_sync_status"] == "synced"
        manifest_path = (
            Path(get_settings().warehouse_mock_root)
            / account.address.lower()
            / run["warehouse_run_path"].lstrip("/")
            / "manifest.json"
        )
        assert manifest_path.exists()

        duplicate = client.post("/service/runs", headers=service_headers, json=create_payload)
        assert duplicate.status_code == 200
        assert duplicate.json()["id"] == run["id"]

        context = [{"kind": "warehouse_asset", "warehousePath": "/apps/knowledge.yeying.pub/uploads/source.pdf", "role": "source"}]
        updated = client.put(f"/service/runs/{run['id']}/context", headers=service_headers, json={"context": context})
        assert updated.status_code == 200
        assert updated.json()["context_manifest_json"] == context

        artifact_content = b"# Research report\n\nVerified result.\n"
        artifact = client.post(
            f"/service/runs/{run['id']}/artifacts",
            headers=service_headers,
            data={
                "artifact_key": "final-report",
                "artifact_type": "report",
                "role": "report",
                "status": "final",
                "generated_by": json.dumps({"tool": "report-writer"}),
            },
            files={"file": ("report.md", artifact_content, "text/markdown")},
        )
        assert artifact.status_code == 200
        artifact_payload = artifact.json()
        assert artifact_payload["sha256"] == hashlib.sha256(artifact_content).hexdigest()
        assert artifact_payload["warehouse_path"].endswith("/artifacts/final-report.md")

        completed = client.post(f"/service/runs/{run['id']}/complete", headers=service_headers, json={})
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["finished_at"]
        manifest = json.loads(manifest_path.read_text())
        assert manifest["status"] == "completed"
        assert manifest["artifacts"][0]["key"] == "final-report"

        repeated = client.post(f"/service/runs/{run['id']}/complete", headers=service_headers, json={})
        assert repeated.status_code == 200
        rejected = client.put(f"/service/runs/{run['id']}/context", headers=service_headers, json={"context": []})
        assert rejected.status_code == 409


def test_agent_run_is_isolated_by_principal_and_revocation():
    with TestClient(app) as client:
        owner_headers = login(client, Account.create())
        principal_a, key_a = create_principal(client, owner_headers, "chat-a")
        _, key_b = create_principal(client, owner_headers, "chat-b")
        created = client.post(
            "/service/runs",
            headers={"X-Service-Api-Key": key_a},
            json={"external_id": "a-1", "run_type": "research"},
        )
        assert created.status_code == 200
        run_id = created.json()["id"]

        hidden = client.get(f"/service/runs/{run_id}", headers={"X-Service-Api-Key": key_b})
        assert hidden.status_code == 404

        revoked = client.patch(
            f"/service-principals/{principal_a['id']}",
            headers=owner_headers,
            json={"principal_status": "revoked"},
        )
        assert revoked.status_code == 200
        blocked = client.post(
            "/service/runs",
            headers={"X-Service-Api-Key": key_a},
            json={"external_id": "a-2", "run_type": "research"},
        )
        assert blocked.status_code == 403


def test_agent_run_context_rejects_ungranted_knowledge_reference_and_owner_can_retry_manifest():
    with TestClient(app) as client:
        account = Account.create()
        owner_headers = login(client, account)
        _, api_key = create_principal(client, owner_headers, "context-check")
        service_headers = {"X-Service-Api-Key": api_key}
        created = client.post(
            "/service/runs",
            headers=service_headers,
            json={"external_id": "context-1", "run_type": "research"},
        )
        assert created.status_code == 200
        run = created.json()
        assert run["manifest_sync_status"] == "failed"

        denied = client.put(
            f"/service/runs/{run['id']}/context",
            headers=service_headers,
            json={"context": [{"kind": "evidence", "referenceId": "999999", "role": "citation"}]},
        )
        assert denied.status_code == 409

        configure_warehouse_credentials(client, owner_headers)
        retried = client.post(f"/runs/{run['id']}/manifest/retry", headers=owner_headers)
        assert retried.status_code == 200
        assert retried.json()["manifest_sync_status"] == "synced"
