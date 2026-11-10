from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.core.settings import get_settings
from knowledge.models import WarehouseToolCredential
from knowledge.services.warehouse_scope import warehouse_app_root
from knowledge.utils.time import utc_now


TOOL_CREDENTIAL_NAME = "knowledge-agent-runs"
TOOL_CREDENTIAL_SCOPES = ["asset:read", "asset:write"]


@dataclass(frozen=True)
class ToolCredentialSummary:
    credential_id: str
    scopes: list[str]
    path_prefixes: list[str]
    expires_at: datetime
    status: str


class WarehouseToolCredentialError(ValueError):
    pass


class WarehouseToolCredentialService:
    """Create and store a Warehouse scoped Tool credential for one wallet owner."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self.settings = get_settings()
        self.fernet = Fernet(self.settings.token_encryption_secret.encode("utf-8"))
        self.client = client or httpx.Client(timeout=httpx.Timeout(20.0))

    @property
    def base_url(self) -> str:
        return (self.settings.warehouse_api_base_url or self.settings.warehouse_base_url).rstrip("/")

    def connect(self, db: Session, wallet_address: str, warehouse_jwt: str) -> ToolCredentialSummary:
        wallet = wallet_address.strip().lower()
        token = warehouse_jwt.strip()
        if not token:
            raise WarehouseToolCredentialError("Warehouse login is required")
        headers = {"Authorization": f"Bearer {token}"}
        user = self._request("GET", "/api/v1/public/webdav/user/info", headers=headers)
        warehouse_wallet = str(user.get("wallet_address") or "").strip().lower()
        if not warehouse_wallet or warehouse_wallet != wallet:
            raise WarehouseToolCredentialError("Warehouse login wallet does not match the Knowledge account")

        root = warehouse_app_root(self.settings).rstrip("/")
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        path = "/api/v1/public/tools/credentials"
        rows_payload = self._request("GET", path, headers=headers)
        rows = rows_payload.get("items") if isinstance(rows_payload, dict) else None
        existing = next(
            (row for row in rows or [] if isinstance(row, dict) and row.get("name") == TOOL_CREDENTIAL_NAME),
            None,
        )

        if existing:
            scopes = sorted(str(value) for value in existing.get("scopes", []))
            prefixes = [str(value) for value in existing.get("pathPrefixes", [])]
            if scopes != sorted(TOOL_CREDENTIAL_SCOPES) or prefixes != [root]:
                raise WarehouseToolCredentialError(
                    "An existing Knowledge Tool credential has a different scope; revoke it in Warehouse before reconnecting"
                )
            credential_id = str(existing.get("id") or "")
            payload = self._request(
                "POST",
                f"{path}/{credential_id}/rotate",
                headers=headers,
                json={"expiresAt": expires_at.isoformat()},
            )
        else:
            payload = self._request(
                "POST",
                path,
                headers=headers,
                json={
                    "name": TOOL_CREDENTIAL_NAME,
                    "scopes": TOOL_CREDENTIAL_SCOPES,
                    "pathPrefixes": [root],
                    "expiresAt": expires_at.isoformat(),
                },
            )

        credential_id = str(payload.get("id") or "")
        secret = str(payload.get("secret") or "")
        if not credential_id or not secret.startswith("wts_"):
            raise WarehouseToolCredentialError("Warehouse returned an invalid Tool credential")

        current = db.scalar(
            select(WarehouseToolCredential).where(WarehouseToolCredential.owner_wallet_address == wallet)
        )
        if current is None:
            current = WarehouseToolCredential(
                owner_wallet_address=wallet,
                warehouse_credential_id=credential_id,
                encrypted_secret=self._encrypt(secret),
                scopes=TOOL_CREDENTIAL_SCOPES,
                path_prefixes=[root],
                expires_at=expires_at.replace(tzinfo=None),
                status="active",
            )
            db.add(current)
        else:
            current.warehouse_credential_id = credential_id
            current.encrypted_secret = self._encrypt(secret)
            current.scopes = TOOL_CREDENTIAL_SCOPES
            current.path_prefixes = [root]
            current.expires_at = expires_at.replace(tzinfo=None)
            current.status = "active"
        try:
            db.commit()
            db.refresh(current)
        except Exception:
            # A successful remote rotation invalidates the previously stored
            # secret. Revoke the replacement if Knowledge cannot persist it,
            # then clear any stale local secret when the database recovers.
            db.rollback()
            try:
                self._request(
                    "POST",
                    f"{path}/{credential_id}/revoke",
                    headers=headers,
                    expected=(200, 204, 404),
                )
            except WarehouseToolCredentialError:
                pass
            try:
                stale = db.scalar(
                    select(WarehouseToolCredential).where(
                        WarehouseToolCredential.owner_wallet_address == wallet
                    )
                )
                if stale is not None:
                    stale.status = "revoked"
                    stale.encrypted_secret = ""
                    db.commit()
            except Exception:
                db.rollback()
            raise
        return self.summarize(current)

    def disconnect(self, db: Session, wallet_address: str, warehouse_jwt: str) -> None:
        current = db.scalar(
            select(WarehouseToolCredential).where(
                WarehouseToolCredential.owner_wallet_address == wallet_address.strip().lower()
            )
        )
        if current is None:
            return
        headers = {"Authorization": f"Bearer {warehouse_jwt.strip()}"}
        user = self._request("GET", "/api/v1/public/webdav/user/info", headers=headers)
        if str(user.get("wallet_address") or "").strip().lower() != wallet_address.strip().lower():
            raise WarehouseToolCredentialError("Warehouse login wallet does not match the Knowledge account")
        self._request(
            "POST",
            f"/api/v1/public/tools/credentials/{current.warehouse_credential_id}/revoke",
            headers=headers,
            # A user may have revoked the credential directly in Warehouse.
            # In that case deleting the local secret is still safe and useful.
            expected=(200, 204, 404),
        )
        current.status = "revoked"
        current.encrypted_secret = ""
        db.commit()

    def get(self, db: Session, wallet_address: str) -> ToolCredentialSummary | None:
        current = db.scalar(
            select(WarehouseToolCredential).where(
                WarehouseToolCredential.owner_wallet_address == wallet_address.strip().lower()
            )
        )
        return self.summarize(current) if current is not None else None

    def get_secret(self, db: Session, wallet_address: str) -> str | None:
        current = db.scalar(
            select(WarehouseToolCredential)
            .where(WarehouseToolCredential.owner_wallet_address == wallet_address.strip().lower())
            .where(WarehouseToolCredential.status == "active")
        )
        if current is None or current.expires_at <= utc_now():
            return None
        return self.fernet.decrypt(current.encrypted_secret.encode("utf-8")).decode("utf-8")

    @staticmethod
    def summarize(current: WarehouseToolCredential) -> ToolCredentialSummary:
        return ToolCredentialSummary(
            credential_id=current.warehouse_credential_id,
            scopes=list(current.scopes or []),
            path_prefixes=list(current.path_prefixes or []),
            expires_at=current.expires_at,
            status=current.status,
        )

    def _request(self, method: str, path: str, *, headers: dict[str, str], json: dict | None = None, expected=(200,)) -> dict:
        try:
            response = self.client.request(method, f"{self.base_url}{path}", headers=headers, json=json)
        except httpx.HTTPError as exc:
            raise WarehouseToolCredentialError("Warehouse credential service is unavailable") from exc
        if response.status_code not in expected:
            raise WarehouseToolCredentialError(f"Warehouse credential request failed ({response.status_code})")
        if response.status_code in {204, 404}:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise WarehouseToolCredentialError("Warehouse returned an invalid credential response") from exc
        if not isinstance(payload, dict):
            raise WarehouseToolCredentialError("Warehouse returned an invalid credential response")
        return payload

    def _encrypt(self, secret: str) -> str:
        return self.fernet.encrypt(secret.encode("utf-8")).decode("utf-8")
