from __future__ import annotations

from fastapi.testclient import TestClient

from knowledge.api import routes_auth
from knowledge.main import app


def test_passkey_login_exchanges_identity_code_only_on_the_server(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(routes_auth.passport_service.settings, "identity_node_url", "https://passport.example.test")
    monkeypatch.setattr(routes_auth.passport_service.settings, "identity_app_id", "knowledge-local")
    monkeypatch.setattr(routes_auth.passport_service.settings, "identity_redirect_uri", "http://testserver/auth/passport/callback")
    monkeypatch.setattr(routes_auth.passport_service.settings, "identity_trust_dir", "")
    calls: list[tuple[str, str, dict]] = []

    def node_request(method: str, path: str, payload: dict) -> dict:
        calls.append((method, path, payload))
        if path.endswith("/request"):
            return {
                "requestId": "request-1",
                "verifyUrl": "https://passport.example.test/identity/authorize?requestId=request-1",
                "audience": "http://testserver",
                "nonce": "nonce-1",
                "scopes": ["identity.basic", "identity.wallet", "identity.username", "identity.email"],
            }
        assert payload["code"] == "single-use-code"
        assert payload["codeVerifier"]
        return {
            "did": "did:yeying:wid_12345678901234567890123456789012",
            "walletAddress": "0x1111111111111111111111111111111111111111",
            "state": calls[0][2]["state"],
            "scopes": ["identity.basic", "identity.wallet", "identity.username", "identity.email"],
            "credentials": [
                {"type": "WalletAccountCredential", "subject": {"address": "0x1111111111111111111111111111111111111111", "chainKey": "eip155:1"}},
                {"type": "UsernameCredential", "subject": {"username": "alice"}},
                {"type": "EmailCredential", "subject": {"email": "alice@example.test"}},
            ],
        }

    monkeypatch.setattr(routes_auth.passport_service, "_node_request", node_request)
    with TestClient(app) as client:
        created = client.post("/auth/passport/sessions")
        assert created.status_code == 200
        session = created.json()
        assert session["verify_url"].endswith("request-1")
        assert "codeVerifier" not in session

        pending = client.get(f"/auth/passport/sessions/{session['session_id']}")
        assert pending.json() == {"status": "pending", "token": None}

        callback_state = calls[0][2]["state"]
        callback = client.get(f"/auth/passport/callback?state={callback_state}&code=single-use-code")
        assert callback.status_code == 200
        assert "window.close" in callback.text
        completed = client.get(f"/auth/passport/sessions/{session['session_id']}")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["token"]["wallet_address"] == "0x1111111111111111111111111111111111111111"
        assert completed.json()["token"]["did"] == "did:yeying:wid_12345678901234567890123456789012"

    assert [path for _, path, _ in calls] == [
        "/api/v1/public/identity/authorize/request",
        "/api/v1/public/identity/authorize/exchange",
    ]
    assert calls[0][2]["codeChallengeMethod"] == "S256"
    assert calls[0][2]["scopes"] == ["identity.basic", "identity.wallet", "identity.username", "identity.email"]
