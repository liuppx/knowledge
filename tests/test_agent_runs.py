from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from pathlib import Path
import hashlib
import io
import json
from zipfile import ZipFile

from knowledge.main import app
from knowledge.core.settings import get_settings
from knowledge.workers.runner import Worker
from knowledge.services.spreadsheet_analysis import SpreadsheetAnalysisService
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


def test_spreadsheet_analysis_run_is_processed_by_worker():
    with TestClient(app) as client:
        account = Account.create()
        owner_headers = login(client, account)
        configure_warehouse_credentials(client, owner_headers)
        _, api_key = create_principal(client, owner_headers, "community-chat-spreadsheet")
        service_headers = {"X-Service-Api-Key": api_key}
        csv_content = b"region,amount,active\neast,42,true\nwest,18,false\neast,,true\n"
        upload = client.post(
            "/warehouse/upload",
            headers=owner_headers,
            data={"target_dir": "/apps/knowledge.yeying.pub/uploads"},
            files={"file": ("sales.csv", csv_content, "text/csv")},
        )
        assert upload.status_code == 200
        source_path = upload.json()["warehouse_path"]
        created = client.post(
            "/service/runs",
            headers=service_headers,
            json={
                "session_id": "chat-session-csv",
                "external_id": "chat-session-csv:message-1",
                "run_type": "spreadsheet_analysis",
                "inputs": [
                    {
                        "kind": "warehouse_asset",
                        "warehousePath": source_path,
                        "size": len(csv_content),
                        "contentType": "text/csv",
                    }
                ],
                "intent": "检查销售数据结构和空值",
                "constraints": {
                    "analysis_plan": {
                        "group_by": ["region"],
                        "aggregations": [{"column": "amount", "op": "sum", "alias": "total_amount"}],
                        "sort": [{"column": "total_amount", "direction": "desc"}],
                    }
                },
            },
        )
        assert created.status_code == 200
        run = created.json()
        assert run["status"] == "queued"

        inputs = client.get(f"/service/runs/{run['id']}/inputs", headers=service_headers)
        assert inputs.status_code == 200
        assert inputs.json()[0]["sha256"] == ""

        assert Worker().process_once() == 1

        completed = client.get(f"/service/runs/{run['id']}", headers=service_headers)
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        frozen_inputs = client.get(f"/service/runs/{run['id']}/inputs", headers=service_headers).json()
        assert frozen_inputs[0]["sha256"] == hashlib.sha256(csv_content).hexdigest()
        events = client.get(f"/service/runs/{run['id']}/events", headers=service_headers).json()
        assert [item["event_type"] for item in events] == [
            "run.queued",
            "run.started",
            "run.progress",
            "run.progress",
            "run.progress",
            "run.progress",
            "run.completed",
        ]
        assert [item["sequence"] for item in events] == list(range(1, len(events) + 1))
        streamed = client.get(
            f"/service/runs/{run['id']}/events",
            headers={**service_headers, "Accept": "text/event-stream"},
        )
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith("text/event-stream")
        assert [f"id: {item['sequence']}" for item in events] == [
            line for line in streamed.text.splitlines() if line.startswith("id: ")
        ]
        resumed = client.get(
            f"/service/runs/{run['id']}/events",
            headers={
                **service_headers,
                "Accept": "text/event-stream",
                "Last-Event-ID": str(events[2]["sequence"]),
            },
        )
        assert resumed.status_code == 200
        assert [f"id: {item['sequence']}" for item in events[3:]] == [
            line for line in resumed.text.splitlines() if line.startswith("id: ")
        ]
        steps = client.get(f"/service/runs/{run['id']}/steps", headers=service_headers).json()
        assert [item["step_type"] for item in steps] == ["resolve", "profile", "plan", "execute", "publish"]
        assert all(item["status"] == "completed" for item in steps)
        artifacts = client.get(f"/service/runs/{run['id']}/artifacts", headers=service_headers).json()
        assert {item["artifact_key"] for item in artifacts} == {
            "analysis-plan",
            "chart",
            "profile",
            "result",
            "result-xlsx",
            "summary",
        }
        profile_artifact = next(item for item in artifacts if item["artifact_key"] == "profile")
        profile_path = (
            Path(get_settings().warehouse_mock_root)
            / account.address.lower()
            / profile_artifact["warehouse_path"].lstrip("/")
        )
        profile = json.loads(profile_path.read_text())
        assert profile["format"] == "csv"
        assert profile["rowCount"] == 3
        assert profile["columnCount"] == 3
        assert profile["columns"][1]["nullCount"] == 1
        assert profile["analysis"] == {"mode": "group_aggregate", "resultRowCount": 2}
        result_artifact = next(item for item in artifacts if item["artifact_key"] == "result")
        result_path = (
            Path(get_settings().warehouse_mock_root)
            / account.address.lower()
            / result_artifact["warehouse_path"].lstrip("/")
        )
        result_text = result_path.read_text(encoding="utf-8-sig")
        assert result_text.splitlines() == ["region,total_amount", "east,42", "west,18"]
        xlsx_artifact = next(item for item in artifacts if item["artifact_key"] == "result-xlsx")
        assert xlsx_artifact["content_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        chart_artifact = next(item for item in artifacts if item["artifact_key"] == "chart")
        chart_path = (
            Path(get_settings().warehouse_mock_root)
            / account.address.lower()
            / chart_artifact["warehouse_path"].lstrip("/")
        )
        assert chart_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        manifest_path = (
            Path(get_settings().warehouse_mock_root)
            / account.address.lower()
            / completed.json()["warehouse_run_path"].lstrip("/")
            / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text())
        assert manifest["inputs"][0]["sha256"] == hashlib.sha256(csv_content).hexdigest()


def test_spreadsheet_analysis_rejects_non_spreadsheet_input():
    with TestClient(app) as client:
        owner_headers = login(client, Account.create())
        _, api_key = create_principal(client, owner_headers, "spreadsheet-validation")
        response = client.post(
            "/service/runs",
            headers={"X-Service-Api-Key": api_key},
            json={
                "run_type": "spreadsheet_analysis",
                "inputs": [{"kind": "warehouse_asset", "warehousePath": "/apps/knowledge.yeying.pub/uploads/readme.txt"}],
            },
        )
        assert response.status_code == 400
        assert "CSV or XLSX" in response.json()["detail"]


def test_spreadsheet_analysis_profiles_basic_xlsx_without_executing_formulas():
    payload = io.BytesIO()
    with ZipFile(payload, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Sales" sheetId="1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>region</t></si><si><t>amount</t></si><si><t>east</t></si></sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
            '<row r="2"><c t="s"><v>2</v></c><c><f>21*2</f><v>42</v></c></row></sheetData></worksheet>',
        )

    profile = SpreadsheetAnalysisService()._profile_xlsx(payload.getvalue())
    assert profile["format"] == "xlsx"
    assert profile["sheetCount"] == 1
    assert profile["rowCount"] == 1
    assert profile["columns"][0]["name"] == "region"
    assert profile["columns"][1]["inferredType"] == "integer"
    assert "does not recalculate formulas" in profile["limitations"][0]
