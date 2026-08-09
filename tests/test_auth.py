from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from knowledge.main import app


def test_siwe_challenge_accepts_web3_bs_fields_and_issues_token() -> None:
    with TestClient(app) as client:
        account = Account.create()
        challenge = client.post("/auth/challenge", json={"address": account.address})
        assert challenge.status_code == 200
        payload = challenge.json()
        assert payload["challenge"] == payload["message"]
        assert payload["challenge"].startswith(f"testserver wants you to sign in with your Ethereum account:\n{account.address.lower()}\n\n")
        assert "URI: http://testserver" in payload["challenge"]
        assert "Version: 1" in payload["challenge"]
        assert "Chain ID: 1" in payload["challenge"]
        assert f"Nonce: {payload['nonce']}" in payload["challenge"]
        assert "Issued At: " in payload["challenge"]
        assert "Expiration Time: " in payload["challenge"]

        signature = account.sign_message(encode_defunct(text=payload["challenge"])).signature.hex()
        verified = client.post("/auth/verify", json={"address": account.address, "signature": signature})
        assert verified.status_code == 200
        token = verified.json()
        assert token["token"] == token["access_token"]
        assert token["wallet_address"] == account.address.lower()

