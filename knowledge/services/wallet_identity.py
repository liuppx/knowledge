from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from eth_utils import to_checksum_address


IDENTITY_SCOPES = ["identity.basic", "identity.wallet", "identity.username", "identity.email"]
SCOPES_WITH_AVATAR = [*IDENTITY_SCOPES, "identity.avatar"]
SCOPE_CREDENTIALS = {
    "identity.wallet": "WalletAccountCredential",
    "identity.username": "UsernameCredential",
    "identity.email": "EmailCredential",
    "identity.avatar": "AvatarCredential",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical(value: Any) -> str:
    if value is None or isinstance(value, (str, bool, int)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("identity presentation contains unsupported data")
        return json.dumps(0 if value == 0 else value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_canonical(value[key])}"
            for key in sorted(value)
        ) + "}"
    raise ValueError("identity presentation contains unsupported data")


def _verify_signature(public_key: str, signature: str, payload: Any, error_code: str) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(_b64decode(public_key)).verify(
            _b64decode(signature), _canonical(payload).encode("utf-8")
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(error_code) from exc


def _controller(document: dict[str, Any], method: str, did: str, purpose: str) -> dict[str, Any]:
    controllers = document.get("controllers")
    if not isinstance(controllers, list):
        raise ValueError("IDENTITY_DOCUMENT_INVALID")
    for item in controllers:
        controller_id = item.get("controllerId", item.get("id")) if isinstance(item, dict) else None
        if (
            method == f"{did}#{controller_id}"
            and isinstance(item, dict)
            and item.get("status") == "active"
            and isinstance(item.get("purposes"), list)
            and purpose in item["purposes"]
        ):
            return item
    raise ValueError("IDENTITY_CONTROLLER_NOT_AUTHORIZED")


def _verify_document(document: dict[str, Any], did: str) -> None:
    if document.get("version") != 1 or document.get("id") != did or not isinstance(document.get("controllers"), list):
        raise ValueError("IDENTITY_DOCUMENT_INVALID")
    proof = document.get("proof") or {}
    if not isinstance(proof, dict):
        raise ValueError("IDENTITY_DOCUMENT_PROOF_INVALID")
    if proof.get("type") != "YeyingIdentityDocumentProofV1" or proof.get("purpose") != "manage":
        raise ValueError("IDENTITY_DOCUMENT_PROOF_INVALID")
    controller = _controller(document, str(proof.get("verificationMethod", "")), did, "manage")
    _verify_signature(
        controller["publicKey"], proof.get("proofValue", ""),
        {key: value for key, value in document.items() if key != "proof"},
        "IDENTITY_DOCUMENT_PROOF_INVALID",
    )


def load_trust_bundle(directory: str | Path | None) -> tuple[str, dict[str, Any]]:
    if not directory:
        raise ValueError("IDENTITY_TRUST_DIR 未配置")
    root = Path(directory)
    try:
        metadata_bytes = (root / "issuer-metadata.json").read_bytes()
        jwks_bytes = (root / "jwks.json").read_bytes()
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        metadata = json.loads(metadata_bytes)
        jwks = json.loads(jwks_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("身份发行方信任包不可用") from exc
    if not isinstance(metadata, dict) or not isinstance(manifest, dict) or not isinstance(jwks, dict):
        raise ValueError("身份发行方配置无效")
    if (
        hashlib.sha256(metadata_bytes).hexdigest() != manifest.get("metadataSha256")
        or hashlib.sha256(jwks_bytes).hexdigest() != manifest.get("jwksSha256")
    ):
        raise ValueError("身份发行方信任包校验失败")
    issuer = str(metadata.get("issuer", "")).strip()
    if not issuer or issuer != manifest.get("issuer") or not isinstance(jwks.get("keys"), list):
        raise ValueError("身份发行方配置无效")
    return issuer, jwks


def _verify_credential(token: str, did: str, issuer: str, jwks: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    try:
        header_part, payload_part, signature_part = token.split(".")
        header = json.loads(_b64decode(header_part))
        claims = json.loads(_b64decode(payload_part))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("identity_credential_invalid") from exc
    if not isinstance(header, dict) or not isinstance(claims, dict) or header.get("alg") != "EdDSA" or not header.get("kid"):
        raise ValueError("identity_credential_alg_invalid")
    key = next((
        item for item in jwks["keys"]
        if isinstance(item, dict) and item.get("kid") == header["kid"] and item.get("kty") == "OKP" and item.get("crv") == "Ed25519"
    ), None)
    if key is None:
        raise ValueError("identity_issuer_jwks_invalid")
    try:
        Ed25519PublicKey.from_public_bytes(_b64decode(key["x"])).verify(
            _b64decode(signature_part), f"{header_part}.{payload_part}".encode("ascii")
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError("identity_credential_invalid") from exc
    now = int(time.time())
    if claims.get("iss") != issuer or claims.get("sub") != did or not claims.get("jti"):
        raise ValueError("identity_credential_subject_mismatch")
    expires_at = claims.get("exp")
    not_before = claims.get("nbf", 0)
    if (
        not isinstance(expires_at, (int, float)) or isinstance(expires_at, bool) or expires_at <= now
        or not isinstance(not_before, (int, float)) or isinstance(not_before, bool) or not_before > now
    ):
        raise ValueError("identity_credential_expired")
    vc = claims.get("vc") or {}
    if not isinstance(vc, dict):
        raise ValueError("identity_credential_type_mismatch")
    types = vc.get("type", [])
    credential_type = next((item for item in types if isinstance(item, str) and item != "VerifiableCredential"), "") if isinstance(types, list) else ""
    subject = vc.get("credentialSubject") or {}
    if not isinstance(subject, dict):
        raise ValueError("identity_credential_type_mismatch")
    if not credential_type or subject.get("id") != did:
        raise ValueError("identity_credential_type_mismatch")
    return credential_type, subject


def verify_credentials(
    credentials: list[Any], did: str, scopes: list[str], trust_dir: str | Path | None,
) -> dict[str, dict[str, Any]]:
    issuer, jwks = load_trust_bundle(trust_dir)
    verified: dict[str, dict[str, Any]] = {}
    for item in credentials:
        token = item.get("credential") if isinstance(item, dict) else item
        if isinstance(token, str) and token:
            kind, subject = _verify_credential(token, did, issuer, jwks)
            verified[kind] = subject
    for scope in scopes:
        required = SCOPE_CREDENTIALS.get(scope)
        if required and required not in verified:
            raise ValueError(f"identity_credential_required:{required}")
    return verified


def verify_presentation(
    presentation: dict[str, Any], *, audience: str, nonce: str, scopes: list[str], trust_dir: str | Path | None,
) -> tuple[str, str, dict[str, dict[str, Any]]]:
    if presentation.get("version") != 1:
        raise ValueError("IDENTITY_PRESENTATION_INVALID")
    did = str(presentation.get("holder", "")).strip()
    if not did.startswith("did:yeying:wid_") or len(did) < 35:
        raise ValueError("IDENTITY_PRESENTATION_INVALID")
    presented_scopes = presentation.get("scopes")
    if not isinstance(presented_scopes, list) or any(scope not in presented_scopes for scope in scopes):
        raise ValueError("IDENTITY_PRESENTATION_SCOPE_MISMATCH")
    if presentation.get("audience") != audience or presentation.get("nonce") != nonce:
        raise ValueError("IDENTITY_PRESENTATION_CONTEXT_MISMATCH")
    try:
        issued_at = datetime.fromisoformat(str(presentation["issuedAt"]).replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(str(presentation["expiresAt"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError("IDENTITY_PRESENTATION_EXPIRED") from exc
    if issued_at.tzinfo is None or expires_at.tzinfo is None:
        raise ValueError("IDENTITY_PRESENTATION_EXPIRED")
    if issued_at > _now() + timedelta(seconds=60) or expires_at <= _now() - timedelta(seconds=60):
        raise ValueError("IDENTITY_PRESENTATION_EXPIRED")
    document = presentation.get("identityDocument")
    if not isinstance(document, dict):
        raise ValueError("IDENTITY_PRESENTATION_KEY_MISSING")
    _verify_document(document, did)
    proof = presentation.get("proof") or {}
    if not isinstance(proof, dict):
        raise ValueError("IDENTITY_PRESENTATION_INVALID")
    if proof.get("type") != "YeyingIdentityPresentationProofV1" or proof.get("purpose") != "authentication":
        raise ValueError("IDENTITY_PRESENTATION_INVALID")
    controller = _controller(document, str(proof.get("verificationMethod", "")), did, "authentication")
    _verify_signature(
        controller["publicKey"], proof.get("proofValue", ""),
        {key: value for key, value in presentation.items() if key != "proof"},
        "IDENTITY_PRESENTATION_PROOF_INVALID",
    )
    verified = verify_credentials(presentation.get("credentials") or [], did, scopes, trust_dir)
    wallet = verified.get("WalletAccountCredential", {})
    try:
        address = to_checksum_address(str(wallet.get("address", "")).strip())
    except ValueError as exc:
        raise ValueError("identity_wallet_account_invalid") from exc
    chain = str(wallet.get("chainKey", "")).strip()
    wallet_proof = presentation.get("walletProof") or {}
    if not isinstance(wallet_proof, dict):
        raise ValueError("identity_wallet_account_invalid")
    if (
        address.lower() != str(wallet_proof.get("address", "")).lower()
        or not chain
        or chain.lower() != str(wallet_proof.get("chainKey", "")).lower()
    ):
        raise ValueError("identity_wallet_account_invalid")
    if not str((verified.get("UsernameCredential") or {}).get("username", "")).strip():
        raise ValueError("identity_username_credential_invalid")
    if not str((verified.get("EmailCredential") or {}).get("email", "")).strip():
        raise ValueError("identity_email_credential_invalid")
    return did, address, verified


def verify_exchange_identity(data: dict[str, Any], trust_dir: str | Path | None) -> tuple[str, str, dict[str, dict[str, Any]]]:
    did = str(data.get("did", "")).strip()
    if not did.startswith("did:yeying:wid_") or len(did) < 35:
        raise ValueError("夜莺身份服务未返回有效钱包身份")
    address = str(data.get("walletAddress", data.get("wallet_address", ""))).strip()
    try:
        normalized_address = to_checksum_address(address)
    except ValueError as exc:
        raise ValueError("夜莺身份服务未返回有效钱包账户") from exc
    scopes = data.get("scopes") or []
    if not isinstance(scopes, list) or any(scope not in scopes for scope in IDENTITY_SCOPES):
        raise ValueError("夜莺身份授权范围不完整")
    credentials = data.get("credentials") or []
    if trust_dir:
        verified = verify_credentials(credentials, did, IDENTITY_SCOPES, trust_dir)
    else:
        # The authorization-code response comes from the configured Node
        # service over TLS. Keep the same trust boundary as Router for this
        # server-to-server path: require the returned credential subjects;
        # local wallet presentations still use verify_credentials above.
        verified = {}
        for credential in credentials:
            if not isinstance(credential, dict):
                continue
            kind = str(credential.get("type", "")).strip()
            if kind:
                subject = credential.get("subject") or {}
                token = credential.get("credential")
                if isinstance(token, str) and token.count(".") == 2:
                    try:
                        claims = json.loads(_b64decode(token.split(".")[1]))
                        subject = (claims.get("vc") or {}).get("credentialSubject") or {}
                        if claims.get("sub") != did or subject.get("id") != did:
                            raise ValueError("identity_credential_subject_mismatch")
                    except (ValueError, json.JSONDecodeError, AttributeError) as exc:
                        raise ValueError("identity_credential_invalid") from exc
                if not isinstance(subject, dict):
                    raise ValueError("identity_credential_invalid")
                verified[kind] = subject
        required = {"WalletAccountCredential", "UsernameCredential", "EmailCredential"}
        if not required.issubset(verified):
            raise ValueError("夜莺身份未返回完整的账户、用户名和邮箱凭证")
    wallet = verified.get("WalletAccountCredential") or {}
    if str(wallet.get("address", "")).lower() != normalized_address.lower() or not wallet.get("chainKey"):
        raise ValueError("夜莺身份账户凭证无效")
    if not str((verified.get("UsernameCredential") or {}).get("username", "")).strip():
        raise ValueError("夜莺身份未返回用户名")
    if not str((verified.get("EmailCredential") or {}).get("email", "")).strip():
        raise ValueError("夜莺身份未返回已验证邮箱")
    return did, normalized_address, verified
