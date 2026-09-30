from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from knowledge.main import app


def _login(client: TestClient, account) -> str:
    challenge = client.post("/auth/challenge", json={"wallet_address": account.address}).json()
    message = encode_defunct(text=challenge["message"])
    signed = Account.sign_message(message, account.key)
    verify = client.post(
        "/auth/verify",
        json={"wallet_address": account.address, "signature": signed.signature.hex()},
    )
    verify.raise_for_status()
    return verify.json()["access_token"]


def test_reindex_units_endpoint_is_owner_scoped_and_idempotent():
    client = TestClient(app)
    account = Account.create()
    token = _login(client, account)
    headers = {"Authorization": f"Bearer {token}"}

    kb = client.post("/kbs", headers=headers, json={"name": "reindex-kb"})
    kb.raise_for_status()
    kb_id = kb.json()["id"]

    # Fresh KB has no evidence units yet -> a well-formed no-op response.
    response = client.post(f"/kbs/{kb_id}/reindex-units", headers=headers)
    response.raise_for_status()
    payload = response.json()
    # No Weaviate configured under the test's db backend -> weaviate mirror is null.
    assert payload == {"kb_id": kb_id, "kind": "evidence", "indexed": 0, "skipped": 0, "weaviate": None}


def test_reindex_units_rejects_foreign_kb():
    client = TestClient(app)
    owner = Account.create()
    owner_headers = {"Authorization": f"Bearer {_login(client, owner)}"}
    kb = client.post("/kbs", headers=owner_headers, json={"name": "private-kb"})
    kb.raise_for_status()
    kb_id = kb.json()["id"]

    intruder_headers = {"Authorization": f"Bearer {_login(client, Account.create())}"}
    response = client.post(f"/kbs/{kb_id}/reindex-units", headers=intruder_headers)
    assert response.status_code == 404
