from __future__ import annotations

from fastapi.testclient import TestClient

from knowledge.api import routes_auth
from knowledge.main import app


def test_passport_login_exchanges_code_only_on_the_server(monkeypatch) -> None:
    monkeypatch.setattr(routes_auth.passport_service.settings, "passport_node_url", "https://passport.example.test")
    monkeypatch.setattr(routes_auth.passport_service.settings, "passport_app_id", "knowledge-local")
    monkeypatch.setattr(routes_auth.passport_service.settings, "passport_redirect_uri", "http://testserver/auth/passport/callback")
    calls: list[tuple[str, str, dict]] = []

    def node_request(method: str, path: str, payload: dict) -> dict:
        calls.append((method, path, payload))
        if path.endswith("/request"):
            return {"requestId": "request-1", "verifyUrl": "https://passport.example.test/verify/request-1"}
        assert payload["code"] == "single-use-code"
        assert payload["codeVerifier"]
        return {"subjectId": "sub-1", "walletAddress": "0x1111111111111111111111111111111111111111"}

    monkeypatch.setattr(routes_auth.passport_service, "_node_request", node_request)
    with TestClient(app) as client:
        created = client.post("/auth/passport/sessions")
        assert created.status_code == 200
        session = created.json()
        assert session["verify_url"].endswith("request-1")
        assert "codeVerifier" not in session

        pending = client.get(f"/auth/passport/sessions/{session['session_id']}")
        assert pending.json() == {"status": "pending", "token": None}

        callback = client.get(f"/auth/passport/callback?state={session['session_id']}&code=single-use-code")
        assert callback.status_code == 200
        completed = client.get(f"/auth/passport/sessions/{session['session_id']}")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["token"]["wallet_address"] == "0x1111111111111111111111111111111111111111"

    assert [path for _, path, _ in calls] == [
        "/api/v1/public/auth/passport/authorize/request",
        "/api/v1/public/auth/passport/authorize/exchange",
    ]
