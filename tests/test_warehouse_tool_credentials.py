from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from knowledge.db.session import SessionLocal
from knowledge.models import WarehouseToolCredential
from knowledge.services.warehouse_tool_credentials import WarehouseToolCredentialError, WarehouseToolCredentialService
from knowledge.utils.time import utc_now


WALLET = "0x1111111111111111111111111111111111111111"


def test_connect_validates_wallet_and_persists_only_encrypted_tool_secret():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/user/info"):
            return httpx.Response(200, json={"wallet_address": WALLET})
        if request.url.path.endswith("/credentials") and request.method == "GET":
            return httpx.Response(200, json={"items": []})
        if request.method == "POST" and request.url.path.endswith("/credentials"):
            body = json.loads(request.content)
            assert body["scopes"] == ["asset:read", "asset:write"]
            assert body["pathPrefixes"] == ["/apps/knowledge.yeying.pub"]
            return httpx.Response(
                200,
                json={"id": "wt_test", "secret": "wts_test_secret", "scopes": body["scopes"], "pathPrefixes": body["pathPrefixes"]},
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    service = WarehouseToolCredentialService(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with SessionLocal() as db:
        summary = service.connect(db, WALLET, "warehouse-user-jwt")
        row = db.scalar(select(WarehouseToolCredential).where(WarehouseToolCredential.owner_wallet_address == WALLET))
        assert row is not None
        assert row.encrypted_secret != "wts_test_secret"
        assert service.get_secret(db, WALLET) == "wts_test_secret"
        db.delete(row)
        db.commit()

    assert summary.credential_id == "wt_test"
    assert summary.status == "active"
    assert requests[0].headers["Authorization"] == "Bearer warehouse-user-jwt"


def test_connect_rejects_warehouse_session_for_a_different_wallet():
    service = WarehouseToolCredentialService(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"wallet_address": "0x2222222222222222222222222222222222222222"})
            )
        )
    )
    with SessionLocal() as db, pytest.raises(WarehouseToolCredentialError, match="does not match"):
        service.connect(db, WALLET, "another-wallet-jwt")


def test_disconnect_revokes_remote_credential_and_clears_local_secret():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/user/info"):
            return httpx.Response(200, json={"wallet_address": WALLET})
        if request.url.path.endswith("/wt_test/revoke"):
            return httpx.Response(204)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    service = WarehouseToolCredentialService(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with SessionLocal() as db:
        row = WarehouseToolCredential(
            owner_wallet_address=WALLET,
            warehouse_credential_id="wt_test",
            encrypted_secret=service._encrypt("wts_secret"),
            scopes=["asset:read", "asset:write"],
            path_prefixes=["/apps/knowledge.yeying.pub"],
            expires_at=utc_now() + timedelta(days=10),
            status="active",
        )
        db.add(row)
        db.commit()

        service.disconnect(db, WALLET, "warehouse-user-jwt")
        db.refresh(row)
        assert row.status == "revoked"
        assert row.encrypted_secret == ""
        assert service.get_secret(db, WALLET) is None

    assert calls[-1].method == "POST"
    assert calls[-1].headers["Authorization"] == "Bearer warehouse-user-jwt"


def test_disconnect_clears_local_secret_when_warehouse_already_revoked_credential():
    wallet = "0x3333333333333333333333333333333333333333"
    credential_id = f"wt_missing_{uuid4().hex}"

    def handler(request):
        if request.url.path.endswith("/user/info"):
            return httpx.Response(200, json={"wallet_address": wallet})
        if request.url.path.endswith(f"/{credential_id}/revoke"):
            return httpx.Response(404)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    service = WarehouseToolCredentialService(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with SessionLocal() as db:
        row = WarehouseToolCredential(
            owner_wallet_address=wallet,
            warehouse_credential_id=credential_id,
            encrypted_secret=service._encrypt("wts_secret"),
            scopes=["asset:read", "asset:write"],
            path_prefixes=["/apps/knowledge.yeying.pub"],
            expires_at=utc_now() + timedelta(days=10),
            status="active",
        )
        db.add(row)
        db.commit()

        service.disconnect(db, wallet, "warehouse-user-jwt")
        db.refresh(row)
        assert row.status == "revoked"
        assert row.encrypted_secret == ""


def test_connect_revokes_remote_credential_if_local_persistence_fails():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/user/info"):
            return httpx.Response(200, json={"wallet_address": WALLET})
        if request.url.path.endswith("/credentials") and request.method == "GET":
            return httpx.Response(200, json={"items": []})
        if request.url.path.endswith("/credentials") and request.method == "POST":
            return httpx.Response(200, json={"id": "wt_new", "secret": "wts_new_secret"})
        if request.url.path.endswith("/wt_new/revoke"):
            return httpx.Response(204)
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    service = WarehouseToolCredentialService(client=httpx.Client(transport=httpx.MockTransport(handler)))
    with SessionLocal() as db, patch.object(db, "commit", side_effect=RuntimeError("database unavailable")):
        with pytest.raises(RuntimeError, match="database unavailable"):
            service.connect(db, WALLET, "warehouse-user-jwt")

    assert any(request.url.path.endswith("/wt_new/revoke") for request in calls)
