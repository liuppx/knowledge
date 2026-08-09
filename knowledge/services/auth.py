from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse

import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.core.settings import get_settings
from knowledge.models import AuthChallenge, WalletUser
from knowledge.utils.time import utc_now


class AuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def normalize_wallet(wallet_address: str) -> str:
        return wallet_address.strip().lower()

    def create_challenge(self, db: Session, wallet_address: str, *, domain: str, uri: str) -> AuthChallenge:
        wallet_address = self.normalize_wallet(wallet_address)
        domain = str(domain or "").strip()
        uri = str(uri or "").strip()
        if not domain or not uri:
            raise ValueError("SIWE domain and URI are required")
        parsed_uri = urlparse(uri)
        if parsed_uri.scheme not in {"http", "https"} or parsed_uri.netloc != domain:
            raise ValueError("SIWE URI must be an HTTP(S) URI for the configured domain")
        if self.settings.siwe_chain_id < 1:
            raise ValueError("SIWE chain ID must be positive")
        nonce = secrets.token_urlsafe(24)
        expires_at = utc_now() + timedelta(seconds=self.settings.challenge_ttl_seconds)
        message = (
            f"{domain} wants you to sign in with your Ethereum account:\n"
            f"{wallet_address}\n\n"
            "Sign in to Knowledge.\n\n"
            f"URI: {uri}\n"
            "Version: 1\n"
            f"Chain ID: {self.settings.siwe_chain_id}\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {utc_now().isoformat()}Z\n"
            f"Expiration Time: {expires_at.isoformat()}Z"
        )
        challenge = AuthChallenge(
            wallet_address=wallet_address,
            nonce=nonce,
            message=message,
            expires_at=expires_at,
        )
        db.add(challenge)
        db.commit()
        db.refresh(challenge)
        return challenge

    def verify_signature(self, db: Session, wallet_address: str, signature: str) -> WalletUser:
        wallet_address = self.normalize_wallet(wallet_address)
        challenge = db.scalar(
            select(AuthChallenge)
            .where(AuthChallenge.wallet_address == wallet_address)
            .where(AuthChallenge.consumed.is_(False))
            .order_by(AuthChallenge.created_at.desc())
        )
        if challenge is None:
            raise ValueError("challenge not found")
        if challenge.expires_at < utc_now():
            raise ValueError("challenge expired")

        message = encode_defunct(text=challenge.message)
        recovered = Account.recover_message(message, signature=signature)
        if self.normalize_wallet(recovered) != wallet_address:
            raise ValueError("invalid signature")

        challenge.consumed = True
        user = db.get(WalletUser, wallet_address)
        if user is None:
            user = WalletUser(wallet_address=wallet_address)
            db.add(user)
        user.last_login_at = utc_now()
        db.commit()
        db.refresh(user)
        return user

    def _build_token(self, wallet_address: str, token_type: str, minutes: int) -> tuple[str, datetime]:
        expires_at = utc_now() + timedelta(minutes=minutes)
        payload = {
            "sub": wallet_address,
            "wallet_address": wallet_address,
            "type": token_type,
            "exp": expires_at,
            "iat": utc_now(),
        }
        token = jwt.encode(payload, self.settings.jwt_secret, algorithm=self.settings.jwt_algorithm)
        return token, expires_at

    def create_token_pair(self, wallet_address: str) -> tuple[tuple[str, datetime], tuple[str, datetime]]:
        access = self._build_token(wallet_address, "access", self.settings.access_token_expire_minutes)
        refresh = self._build_token(wallet_address, "refresh", self.settings.refresh_token_expire_minutes)
        return access, refresh

    def parse_token(self, token: str, expected_type: str = "access") -> dict:
        payload = jwt.decode(token, self.settings.jwt_secret, algorithms=[self.settings.jwt_algorithm])
        if payload.get("type") != expected_type:
            raise ValueError("invalid token type")
        return payload
