from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from knowledge.api import routes_auth
from knowledge.main import app
from knowledge.services.wallet_identity import IDENTITY_SCOPES, _canonical


DID = "did:yeying:wid_12345678901234567890123456789012"
WALLET = "0x1111111111111111111111111111111111111111"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _sign_json(key: Ed25519PrivateKey, value: dict) -> str:
    return _b64url(key.sign(_canonical(value).encode("utf-8")))


def _identity_bundle(directory) -> dict:
    identity_key = Ed25519PrivateKey.generate()
    issuer_key = Ed25519PrivateKey.generate()
    identity_public = _b64url(identity_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    issuer_public = _b64url(issuer_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    issuer = "https://node.example/identity"
    now = datetime.now(UTC)

    document_unsigned = {
        "version": 1,
        "id": DID,
        "walletIdentityId": "wid_test",
        "controllers": [{
            "controllerId": "key-1",
            "kind": "ed25519",
            "publicKey": identity_public,
            "algorithm": "Ed25519",
            "purposes": ["manage", "authentication"],
            "status": "active",
        }],
    }
    document = {
        **document_unsigned,
        "proof": {
            "type": "YeyingIdentityDocumentProofV1",
            "verificationMethod": f"{DID}#key-1",
            "purpose": "manage",
            "proofValue": _sign_json(identity_key, document_unsigned),
        },
    }

    def credential(kind: str, values: dict) -> str:
        header = _b64url(json.dumps({"alg": "EdDSA", "kid": "issuer-1"}, separators=(",", ":")).encode())
        claims = {
            "iss": issuer,
            "sub": DID,
            "jti": f"credential-{kind}",
            "nbf": int(now.timestamp()) - 5,
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "vc": {"type": ["VerifiableCredential", kind], "credentialSubject": {"id": DID, **values}},
        }
        payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
        signing_input = f"{header}.{payload}"
        signature = _b64url(issuer_key.sign(signing_input.encode("ascii")))
        return f"{signing_input}.{signature}"

    credentials = [
        credential("WalletAccountCredential", {"address": WALLET, "chainKey": "eip155:1"}),
        credential("UsernameCredential", {"username": "alice"}),
        credential("EmailCredential", {"email": "alice@example.test"}),
    ]
    metadata = json.dumps({"issuer": issuer}, separators=(",", ":")).encode()
    jwks = json.dumps({"keys": [{"kty": "OKP", "crv": "Ed25519", "kid": "issuer-1", "x": issuer_public}]}, separators=(",", ":")).encode()
    (directory / "issuer-metadata.json").write_bytes(metadata)
    (directory / "jwks.json").write_bytes(jwks)
    (directory / "manifest.json").write_text(json.dumps({
        "issuer": issuer,
        "metadataSha256": hashlib.sha256(metadata).hexdigest(),
        "jwksSha256": hashlib.sha256(jwks).hexdigest(),
    }), encoding="utf-8")

    def presentation(audience: str, nonce: str) -> dict:
        unsigned = {
            "version": 1,
            "holder": DID,
            "audience": audience,
            "nonce": nonce,
            "issuedAt": now.isoformat(),
            "expiresAt": (now + timedelta(minutes=2)).isoformat(),
            "scopes": IDENTITY_SCOPES,
            "identityDocument": document,
            "walletProof": {"address": WALLET, "chainKey": "eip155:1"},
            "credentials": credentials,
        }
        return {
            **unsigned,
            "proof": {
                "type": "YeyingIdentityPresentationProofV1",
                "verificationMethod": f"{DID}#key-1",
                "purpose": "authentication",
                "proofValue": _sign_json(identity_key, unsigned),
            },
        }

    return {"credentials": credentials, "presentation": presentation}


def _configure_identity(monkeypatch, trust_dir) -> None:
    settings = routes_auth.passport_service.settings
    monkeypatch.setattr(settings, "identity_node_url", "https://node.example")
    monkeypatch.setattr(settings, "identity_app_id", "knowledge-test")
    monkeypatch.setattr(settings, "identity_redirect_uri", "http://testserver/auth/passport/callback")
    monkeypatch.setattr(settings, "identity_trust_dir", str(trust_dir))


def test_wallet_identity_login_verifies_locally_and_consumes_session(monkeypatch, tmp_path) -> None:
    identity = _identity_bundle(tmp_path)
    _configure_identity(monkeypatch, tmp_path)

    def unexpected_node_request(*_args, **_kwargs):
        raise AssertionError("wallet identity login must not use the Node authorization-code endpoints")

    monkeypatch.setattr(routes_auth.passport_service, "_node_request", unexpected_node_request)
    with TestClient(app) as client:
        created_response = client.post("/auth/identity/login/session")
        assert created_response.status_code == 200
        envelope = created_response.json()
        assert envelope["code"] == 0
        created = envelope["data"]
        assert created["scopes"] == IDENTITY_SCOPES
        assert created["audience"] == "http://testserver"
        assert "request_id" not in created

        result = client.post("/auth/identity/login/verify", json={
            "session_id": created["session_id"],
            "presentation": identity["presentation"](created["audience"], created["nonce"]),
        })
        assert result.status_code == 200
        assert result.json()["code"] == 0
        assert result.json()["data"]["did"] == DID
        assert result.json()["data"]["wallet_address"].lower() == WALLET.lower()
        assert "access_token" in result.json()["data"]

        replay = client.post("/auth/identity/login/verify", json={
            "session_id": created["session_id"],
            "presentation": identity["presentation"](created["audience"], created["nonce"]),
        })
        assert replay.status_code == 400


def test_wallet_identity_login_rejects_wrong_audience_before_authentication(monkeypatch, tmp_path) -> None:
    identity = _identity_bundle(tmp_path)
    _configure_identity(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post("/auth/identity/login/session").json()["data"]
        rejected = client.post("/auth/identity/login/verify", json={
            "session_id": created["session_id"],
            "presentation": identity["presentation"]("https://attacker.example", created["nonce"]),
        })
        assert rejected.status_code == 400
        assert "CONTEXT_MISMATCH" in rejected.json()["message"]


def test_wallet_identity_login_rejects_invalid_presentation_proof(monkeypatch, tmp_path) -> None:
    identity = _identity_bundle(tmp_path)
    _configure_identity(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post("/auth/identity/login/session").json()["data"]
        presentation = identity["presentation"](created["audience"], created["nonce"])
        presentation["proof"]["proofValue"] = "invalid-proof"
        rejected = client.post("/auth/identity/login/verify", json={
            "session_id": created["session_id"],
            "presentation": presentation,
        })
        assert rejected.status_code == 400
        assert rejected.json()["code"] == 1
        assert rejected.json()["message"] == "IDENTITY_PRESENTATION_PROOF_INVALID"
