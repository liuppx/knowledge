from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from knowledge.core.settings import get_settings
from knowledge.models import PassportLoginSession, PassportSubject, WalletUser
from knowledge.utils.time import utc_now


class PassportAuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def create_session(self, db: Session) -> PassportLoginSession:
        self._require_configured()
        session_id = secrets.token_urlsafe(32)
        verifier = _base64url(secrets.token_bytes(64))
        challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
        expires_at = utc_now() + timedelta(seconds=self.settings.passport_session_ttl_seconds)
        data = self._node_request(
            "POST",
            "/api/v1/public/auth/passport/authorize/request",
            {
                "appId": self.settings.passport_app_id,
                "redirectUri": self.settings.passport_redirect_uri,
                "state": session_id,
                "codeChallenge": challenge,
                "codeChallengeMethod": "S256",
                "requestTtlMs": self.settings.passport_session_ttl_seconds * 1000,
            },
        )
        request_id = str(data.get("requestId") or data.get("request_id") or "").strip()
        if not request_id:
            raise ValueError("通行证服务未返回授权请求 ID")
        session = PassportLoginSession(
            id=session_id,
            request_id=request_id,
            code_verifier=verifier,
            redirect_uri=self.settings.passport_redirect_uri,
            status="pending",
            expires_at=expires_at,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        session.verify_url = str(data.get("verifyUrl") or data.get("verify_url") or "")
        return session

    def receive_callback(self, db: Session, state: str, code: str) -> PassportLoginSession:
        session = db.get(PassportLoginSession, state)
        if session is None or session.expires_at < utc_now():
            raise LookupError("通行证登录会话已过期")
        if session.status == "completed":
            return session
        session.authorization_code = code
        session.status = "approved"
        db.commit()
        db.refresh(session)
        return session

    def complete_session(self, db: Session, session_id: str) -> PassportLoginSession:
        session = db.get(PassportLoginSession, session_id)
        if session is None or session.expires_at < utc_now():
            raise LookupError("通行证登录会话已过期")
        if session.status == "completed":
            return session
        if not session.authorization_code:
            return session
        identity = self._node_request(
            "POST",
            "/api/v1/public/auth/passport/authorize/exchange",
            {
                "code": session.authorization_code,
                "appId": self.settings.passport_app_id,
                "redirectUri": session.redirect_uri,
                "codeVerifier": session.code_verifier,
            },
        )
        subject_id = str(identity.get("subjectId") or identity.get("subject_id") or "").strip()
        wallet_address = str(identity.get("walletAddress") or identity.get("wallet_address") or "").strip().lower()
        if not subject_id or not wallet_address.startswith("0x"):
            raise ValueError("通行证未返回可用身份")
        binding = db.get(PassportSubject, subject_id)
        if binding is not None:
            wallet_address = binding.wallet_address
        user = db.get(WalletUser, wallet_address)
        if user is None:
            user = WalletUser(wallet_address=wallet_address)
            db.add(user)
            db.flush()
        if binding is None:
            db.add(PassportSubject(subject_id=subject_id, wallet_address=wallet_address))
        user.last_login_at = utc_now()
        session.subject_id = subject_id
        session.wallet_address = wallet_address
        session.status = "completed"
        db.commit()
        db.refresh(session)
        return session

    def _require_configured(self) -> None:
        if not self.settings.passport_node_url or not self.settings.passport_app_id or not self.settings.passport_redirect_uri:
            raise ValueError("夜莺通行证未配置，请设置 PASSPORT_NODE_URL、PASSPORT_APP_ID 和 PASSPORT_REDIRECT_URI")

    def _node_request(self, method: str, path: str, payload: dict) -> dict:
        self._require_configured()
        try:
            response = httpx.request(
                method,
                f"{self.settings.passport_node_url.rstrip('/')}{path}",
                json=payload,
                headers={"Accept": "application/json", "X-YeYing-Client": self.settings.passport_app_id},
                timeout=15,
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ValueError("无法连接夜莺通行证服务") from exc
        if not isinstance(body, dict) or not (body.get("code") == 0 or body.get("ret") == 1):
            message = body.get("message") or body.get("msg") if isinstance(body, dict) else "通行证服务返回异常"
            raise ValueError(str(message or "通行证服务返回异常"))
        data = body.get("data", body)
        return data if isinstance(data, dict) else {}


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
