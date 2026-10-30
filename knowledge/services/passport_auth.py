from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.core.settings import get_settings
from knowledge.models import PassportLoginSession, WalletUser
from knowledge.services.wallet_identity import IDENTITY_SCOPES, load_trust_bundle, verify_exchange_identity, verify_presentation
from knowledge.utils.time import utc_now


def _not_expired(value) -> bool:
    normalized = value.replace(tzinfo=None) if value.tzinfo else value
    return normalized >= utc_now()


class PassportAuthService:
    """Node authorization-code flow for Passkey login and Wallet presentations."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def create_session(self, db: Session) -> PassportLoginSession:
        self._require_configured()
        session_id = secrets.token_urlsafe(32)
        verifier = _base64url(secrets.token_bytes(64))
        challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
        expires_at = utc_now() + timedelta(seconds=self.settings.passport_session_ttl_seconds)
        state = secrets.token_urlsafe(32)
        redirect_uri = self.settings.identity_redirect_uri
        data = self._node_request("POST", "/api/v1/public/identity/authorize/request", {
            "appId": self.settings.identity_app_id,
            "redirectUri": redirect_uri,
            "state": state,
            "codeChallenge": challenge,
            "codeChallengeMethod": "S256",
            "scopes": IDENTITY_SCOPES,
            "requestTtlMs": self.settings.passport_session_ttl_seconds * 1000,
        })
        request_id = str(data.get("requestId") or "").strip()
        verify_url = str(data.get("verifyUrl") or "").strip()
        if not request_id or not verify_url:
            raise ValueError("身份服务未返回完整授权请求")
        session = PassportLoginSession(
            id=session_id,
            request_id=request_id,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            state=state,
            audience=str(data.get("audience") or ""),
            nonce=str(data.get("nonce") or ""),
            scopes=data.get("scopes") or IDENTITY_SCOPES,
            status="pending",
            expires_at=_parse_time(data.get("expiresAt")) or expires_at,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session.verify_url = _normalize_verify_url(self.settings.identity_node_url, verify_url)
        return session

    def create_identity_session(self, db: Session, audience: str | None = None) -> dict:
        """Create a local nonce-bound session for Wallet Identity presentation login."""
        self._require_wallet_identity_configured()
        session_id = secrets.token_urlsafe(32)
        request_id = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(32)
        scopes = list(IDENTITY_SCOPES)
        expires_at = utc_now() + timedelta(seconds=self.settings.passport_session_ttl_seconds)
        callback = urlparse(self.settings.identity_redirect_uri or "")
        resolved_audience = (audience or "").rstrip("/")
        if not resolved_audience:
            resolved_audience = f"{callback.scheme}://{callback.netloc}" if callback.scheme and callback.netloc else ""
        if not resolved_audience.startswith(("http://", "https://")):
            raise ValueError("钱包身份登录来源地址无效")
        session = PassportLoginSession(
            id=session_id,
            request_id=request_id,
            code_verifier="",
            redirect_uri=self.settings.identity_redirect_uri,
            audience=resolved_audience,
            nonce=nonce,
            scopes=scopes,
            status="pending",
            expires_at=expires_at,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return {
            "session_id": session.id,
            "audience": session.audience,
            "nonce": session.nonce,
            "scopes": session.scopes,
            "issuerEndpoint": self.settings.identity_node_url or None,
            "expires_at": session.expires_at.isoformat(),
        }

    def verify_identity(self, db: Session, session_id: str, request_id: str | None, presentation: dict) -> tuple[str, str]:
        session = db.scalar(select(PassportLoginSession).where(PassportLoginSession.id == session_id).with_for_update())
        if session is None or not _not_expired(session.expires_at) or session.status != "pending":
            raise ValueError("钱包身份登录会话已过期或已使用")
        if request_id and request_id != session.request_id:
            raise ValueError("钱包身份登录请求不匹配")
        session.status = "verifying"
        db.commit()
        try:
            did, wallet_address, _credentials = verify_presentation(
                presentation,
                audience=session.audience or "",
                nonce=session.nonce or "",
                scopes=session.scopes or IDENTITY_SCOPES,
                trust_dir=self.settings.identity_trust_dir,
            )
            user = self._resolve_user(db, did, wallet_address)
            user.last_login_at = utc_now()
            session.identity_did = did
            session.wallet_address = user.wallet_address
            session.status = "completed"
            session.code_verifier = ""
            db.commit()
            return user.wallet_address, did
        except Exception:
            db.rollback()
            failed = db.get(PassportLoginSession, session_id)
            if failed is not None and failed.status in {"pending", "verifying"}:
                failed.status = "failed"
                failed.code_verifier = ""
                db.commit()
            raise

    def receive_callback(self, db: Session, state: str, code: str) -> PassportLoginSession:
        session = db.scalar(select(PassportLoginSession).where(PassportLoginSession.state == state).with_for_update())
        if session is None or not _not_expired(session.expires_at) or session.status != "pending":
            raise LookupError("通行证登录会话已过期或已使用")
        session.authorization_code = code
        session.status = "approved"
        db.commit()
        db.refresh(session)
        return session

    def complete_session(self, db: Session, session_id: str) -> PassportLoginSession:
        session = db.scalar(select(PassportLoginSession).where(PassportLoginSession.id == session_id).with_for_update())
        if session is None or not _not_expired(session.expires_at):
            raise LookupError("通行证登录会话已过期")
        if session.status == "completed":
            return session
        if session.status != "approved" or not session.authorization_code:
            return session
        session.status = "exchanging"
        db.commit()
        try:
            identity = self._exchange(session, session.authorization_code)
            did, wallet_address = self._validated_identity(identity, expected_state=session.state)
            user = self._resolve_user(db, did, wallet_address)
            user.last_login_at = utc_now()
            session.identity_did = did
            session.wallet_address = user.wallet_address
            session.status = "completed"
            session.authorization_code = None
            session.code_verifier = ""
            db.commit()
            db.refresh(session)
            return session
        except Exception as exc:
            db.rollback()
            failed = db.get(PassportLoginSession, session_id)
            if failed is not None:
                failed.status = "failed"
                failed.authorization_code = None
                failed.code_verifier = ""
                db.commit()
            if isinstance(exc, ValueError):
                raise
            raise ValueError("夜莺身份授权失败") from exc

    def _exchange(self, session: PassportLoginSession, code: str) -> dict:
        return self._node_request("POST", "/api/v1/public/identity/authorize/exchange", {
            "code": code,
            "appId": self.settings.identity_app_id,
            "redirectUri": session.redirect_uri,
            "codeVerifier": session.code_verifier,
        })

    def _validated_identity(self, identity: dict, *, expected_state: str | None) -> tuple[str, str]:
        if expected_state and identity.get("state") != expected_state:
            raise ValueError("夜莺身份授权 state 不匹配")
        did, wallet_address, _credentials = verify_exchange_identity(identity, self.settings.identity_trust_dir)
        return did, wallet_address

    @staticmethod
    def _resolve_user(db: Session, did: str, wallet_address: str) -> WalletUser:
        user = db.scalar(select(WalletUser).where(WalletUser.identity_did == did))
        if user is not None:
            return user
        user = db.get(WalletUser, wallet_address)
        if user is None:
            user = WalletUser(wallet_address=wallet_address, identity_did=did)
            db.add(user)
            db.flush()
            return user
        if user.identity_did and user.identity_did != did:
            raise ValueError("钱包地址已绑定其他钱包身份")
        user.identity_did = did
        return user

    def _require_configured(self) -> None:
        if not self.settings.identity_node_url or not self.settings.identity_app_id or not self.settings.identity_redirect_uri:
            raise ValueError("身份服务未配置，请设置 IDENTITY_NODE_URL、IDENTITY_APP_ID 和已在 Node 登记的 IDENTITY_REDIRECT_URI")

    def _require_wallet_identity_configured(self) -> None:
        if not self.settings.identity_trust_dir:
            raise ValueError("钱包身份登录未配置，请设置 IDENTITY_TRUST_DIR 指向 Node 的身份发行方信任目录")
        load_trust_bundle(self.settings.identity_trust_dir)

    def _node_request(self, method: str, path: str, payload: dict) -> dict:
        self._require_configured()
        try:
            response = httpx.request(
                method,
                f"{self.settings.identity_node_url.rstrip('/')}{path}",
                json=payload,
                headers={"Accept": "application/json", "X-YeYing-Client": self.settings.identity_app_id},
                timeout=15,
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ValueError("无法连接夜莺身份服务") from exc
        if not response.is_success:
            message = body.get("message") if isinstance(body, dict) else None
            if message and "REDIRECT_URI" in str(message):
                raise ValueError("Node 未授权当前通行证回调地址，请检查应用 redirectUris 配置")
            raise ValueError(str(message or "夜莺身份服务请求失败"))
        if not isinstance(body, dict) or body.get("code") != 0:
            message = body.get("message") if isinstance(body, dict) else "身份服务返回异常"
            raise ValueError(str(message or "身份服务返回异常"))
        data = body.get("data", body)
        return data if isinstance(data, dict) else {}


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _normalize_verify_url(node_url: str, verify_url: str) -> str:
    return urljoin(node_url.rstrip("/") + "/", verify_url)


def _parse_time(value: object):
    if not value:
        return None
    from datetime import UTC, datetime

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
