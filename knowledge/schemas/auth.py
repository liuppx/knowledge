from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field


class ChallengeRequest(BaseModel):
    wallet_address: str = Field(validation_alias=AliasChoices("wallet_address", "address"), min_length=42, max_length=64)


class ChallengeResponse(BaseModel):
    wallet_address: str
    nonce: str
    message: str
    challenge: str
    expires_at: datetime


class VerifyRequest(BaseModel):
    wallet_address: str = Field(validation_alias=AliasChoices("wallet_address", "address"))
    signature: str


class TokenResponse(BaseModel):
    access_token: str
    token: str
    refresh_token: str
    token_type: str = "bearer"
    wallet_address: str
    expires_at: datetime
    refresh_expires_at: datetime
    did: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class PassportSessionResponse(BaseModel):
    session_id: str
    verify_url: str
    status: str
    expires_at: datetime


class PassportStatusResponse(BaseModel):
    status: str
    token: TokenResponse | None = None


class WalletIdentityLoginSession(BaseModel):
    session_id: str
    audience: str
    nonce: str
    scopes: list[str]
    issuerEndpoint: str | None = None
    expires_at: datetime


class WalletIdentityLoginSessionEnvelope(BaseModel):
    code: int = 0
    message: str = "ok"
    data: WalletIdentityLoginSession


class WalletIdentityLoginVerifyRequest(BaseModel):
    session_id: str
    request_id: str | None = None
    presentation: dict


class WalletIdentityLoginResultEnvelope(BaseModel):
    code: int = 0
    message: str = "ok"
    data: TokenResponse
