from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from knowledge.db.session import session_scope
from knowledge.main import app
from knowledge.models import AgentRunArtifact, AgentRunEvent
from knowledge.services.warehouse import build_warehouse_gateway
from knowledge.services.warehouse_scope import warehouse_app_path
from tests.helpers import configure_warehouse_credentials


def _login(client: TestClient) -> tuple[str, dict[str, str]]:
    account = Account.create()
    challenge = client.post("/auth/challenge", json={"wallet_address": account.address}).json()
    signature = account.sign_message(encode_defunct(text=challenge["message"])).signature.hex()
    token = client.post("/auth/verify", json={"wallet_address": account.address, "signature": signature}).json()["access_token"]
    return account.address, {"Authorization": f"Bearer {token}"}


def test_user_can_create_and_list_own_analysis_runs_without_service_key() -> None:
    with TestClient(app) as client:
        _, headers = _login(client)
        created = client.post("/analysis-runs", headers=headers, json={"warehouse_path": "/apps/knowledge.yeying.pub/uploads/sales.csv", "intent": "汇总销售额"})
        assert created.status_code == 200
        assert created.json()["run_type"] == "spreadsheet_analysis"
        assert "api_key" not in created.json()
        listed = client.get("/analysis-runs", headers=headers)
        assert listed.status_code == 200
        assert [run["id"] for run in listed.json()] == [created.json()["id"]]


def test_analysis_events_and_artifacts_are_limited_to_run_owner() -> None:
    with TestClient(app) as client:
        owner_address, owner_headers = _login(client)
        _, other_headers = _login(client)
        configure_warehouse_credentials(client, owner_headers)
        created = client.post(
            "/analysis-runs",
            headers=owner_headers,
            json={"warehouse_path": "/apps/knowledge.yeying.pub/uploads/sales.csv", "intent": "汇总销售额"},
        )
        assert created.status_code == 200
        run_id = created.json()["id"]
        artifact_path = warehouse_app_path(f"runs/{run_id}/artifacts/summary.md")
        gateway = build_warehouse_gateway()
        gateway.upload_file(owner_address, warehouse_app_path(f"runs/{run_id}/artifacts"), "summary.md", b"# Summary\n")
        with session_scope() as db:
            db.add(AgentRunEvent(run_id=run_id, sequence=2, event_type="progress", stage="load", progress=25, message="读取数据"))
            db.add(AgentRunArtifact(
                run_id=run_id,
                artifact_key="summary",
                artifact_type="report",
                role="output",
                status="final",
                warehouse_path=artifact_path,
                file_name="summary.md",
                content_type="text/markdown",
                size=12,
                sha256="a" * 64,
            ))

        events = client.get(f"/analysis-runs/{run_id}/events", headers=owner_headers)
        artifacts = client.get(f"/analysis-runs/{run_id}/artifacts", headers=owner_headers)
        assert events.status_code == 200
        assert any(event["message"] == "读取数据" for event in events.json())
        assert artifacts.status_code == 200
        assert artifacts.json()[0]["file_name"] == "summary.md"

        download = client.get(f"/analysis-runs/{run_id}/artifacts/{artifacts.json()[0]['id']}/download", headers=owner_headers)
        assert download.status_code == 200
        assert download.content == b"# Summary\n"
        assert download.headers["content-type"].startswith("text/markdown")

        assert client.get(f"/analysis-runs/{run_id}/events", headers=other_headers).status_code == 404
        assert client.get(f"/analysis-runs/{run_id}/artifacts", headers=other_headers).status_code == 404
        assert client.get(f"/analysis-runs/{run_id}/artifacts/{artifacts.json()[0]['id']}/download", headers=other_headers).status_code == 404
