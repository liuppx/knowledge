from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from knowledge.main import app


def test_user_can_create_and_list_own_analysis_runs_without_service_key() -> None:
    with TestClient(app) as client:
        account = Account.create()
        challenge = client.post("/auth/challenge", json={"wallet_address": account.address}).json()
        signature = account.sign_message(encode_defunct(text=challenge["message"])).signature.hex()
        token = client.post("/auth/verify", json={"wallet_address": account.address, "signature": signature}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/analysis-runs", headers=headers, json={"warehouse_path": "/apps/knowledge.yeying.pub/uploads/sales.csv", "intent": "汇总销售额"})
        assert created.status_code == 200
        assert created.json()["run_type"] == "spreadsheet_analysis"
        assert "api_key" not in created.json()
        listed = client.get("/analysis-runs", headers=headers)
        assert listed.status_code == 200
        assert [run["id"] for run in listed.json()] == [created.json()["id"]]
