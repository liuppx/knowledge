"""知行图(KnowDoGraph)知识操作的编码与签名校验。

与链上节点逐字节一致(节点 ``node/src/codec.rs`` 的 ``encode_knowledge_op``;JavaScript 参考实现
``tools/explorer/reference/signer.js`` 的 ``encodeOp``)。用途只有一个:服务端提交之前,核对浏览器里
钱包签好的字节**正是**我们准备的那条意图,并且签名对该成员的公钥有效——服务端不接触私钥、不签名。

编码:op = actor:u64 ‖ action ‖ nonce:u64(大端);签名 = ed25519("zhixing-knowledge-op-v1" ‖ op);
提交的是 op ‖ 签名(签名 64 字节)。
"""

from __future__ import annotations

import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGN_DOMAIN = b"zhixing-knowledge-op-v1"
SIGNATURE_LEN = 64

LAYERS = {"foundation": 0, "explanation": 1, "scenario": 2, "application": 3}
CITE_KINDS = {"basis": 0, "see-also": 1, "supersedes": 2}
VERDICTS = {"pass": 0, "needs-revision": 1}
MAX_CITES, MAX_BODIES, MAX_LANG_LEN, MAX_MODEL_ID_LEN = 32, 16, 16, 64


class KdgCodecError(ValueError):
    """意图不合法,或签好的字节与意图不符 / 签名无效。"""


def _u8(v: int) -> bytes:
    return struct.pack(">B", v)


def _u32(v: int) -> bytes:
    if not 0 <= int(v) <= 0xFFFFFFFF:
        raise KdgCodecError(f"u32 out of range: {v}")
    return struct.pack(">I", int(v))


def _u64(v: int) -> bytes:
    if not 0 <= int(v) <= 0xFFFFFFFFFFFFFFFF:
        raise KdgCodecError(f"u64 out of range: {v}")
    return struct.pack(">Q", int(v))


def _hex32(value: str, what: str) -> bytes:
    try:
        raw = bytes.fromhex(str(value))
    except ValueError as exc:
        raise KdgCodecError(f"{what} must be hex") from exc
    if len(raw) != 32:
        raise KdgCodecError(f"{what} must be 32 bytes")
    return raw


def _version_payload(action: dict) -> bytes:
    bodies = action.get("bodies") or []
    if len(bodies) > MAX_BODIES:
        raise KdgCodecError(f"at most {MAX_BODIES} bodies")
    parts = [_u64(len(bodies))]
    for body in bodies:
        lang = str(body.get("lang") or "").encode("utf-8")
        if not lang or len(lang) > MAX_LANG_LEN:
            raise KdgCodecError(f"language tag must be 1-{MAX_LANG_LEN} bytes")
        parts += [_u32(len(lang)), lang, _hex32(body.get("hash"), "body hash")]
    source = action.get("source") or {"type": "human"}
    kind = source.get("type")
    if kind == "human":
        parts.append(_u8(0))
    elif kind in ("model", "model-verified"):
        model = str(source.get("id") or "").encode("utf-8")
        if not model or len(model) > MAX_MODEL_ID_LEN:
            raise KdgCodecError(f"model id must be 1-{MAX_MODEL_ID_LEN} bytes")
        parts += [_u8(1 if kind == "model" else 2), _u32(len(model)), model]
    else:
        raise KdgCodecError("source must be human / model / model-verified")
    cites = action.get("cites") or []
    if len(cites) > MAX_CITES:
        raise KdgCodecError(f"at most {MAX_CITES} cites")
    parts.append(_u64(len(cites)))
    for cite in cites:
        if cite.get("kind") not in CITE_KINDS:
            raise KdgCodecError("cite kind must be basis / see-also / supersedes")
        parts += [_u64(cite["unit"]), _u32(cite["version"]), _u8(CITE_KINDS[cite["kind"]])]
    return b"".join(parts)


def encode_action(action: dict) -> bytes:
    kind = action.get("type")
    if kind == "create":
        if action.get("layer") not in LAYERS:
            raise KdgCodecError("layer must be foundation / explanation / scenario / application")
        return _u8(0) + _u8(LAYERS[action["layer"]]) + _u32(action["domain"]) + _version_payload(action)
    if kind == "publish":
        return _u8(1) + _u64(action["unit"]) + _version_payload(action)
    if kind == "verify":
        if action.get("verdict") not in VERDICTS:
            raise KdgCodecError("verdict must be pass / needs-revision")
        note = _hex32(action["noteHash"], "note hash") if action.get("noteHash") else bytes(32)
        return _u8(2) + _u64(action["unit"]) + _u32(action["version"]) + _u8(VERDICTS[action["verdict"]]) + note
    if kind == "invite":
        return _u8(3) + _hex32(action.get("pubkey"), "pubkey")
    raise KdgCodecError(f"unknown action: {kind}")


def encode_op(actor: int, action: dict, nonce: int) -> bytes:
    """不含签名的操作编码(签名覆盖的就是 SIGN_DOMAIN ‖ 它)。"""
    return _u64(actor) + encode_action(action) + _u64(nonce)


def verify_signed_op(signed: bytes, *, actor: int, action: dict, nonce: int, pubkey_hex: str) -> None:
    """核对钱包签好的 op ‖ 签名:内容必须正是这条意图,签名必须对该公钥有效。不符就抛 KdgCodecError。"""
    if len(signed) <= SIGNATURE_LEN:
        raise KdgCodecError("signed op too short")
    op, signature = signed[:-SIGNATURE_LEN], signed[-SIGNATURE_LEN:]
    if op != encode_op(actor, action, nonce):
        raise KdgCodecError("signed op does not match the prepared intent")
    try:
        Ed25519PublicKey.from_public_bytes(_hex32(pubkey_hex, "pubkey")).verify(signature, SIGN_DOMAIN + op)
    except InvalidSignature as exc:
        raise KdgCodecError("signature is not valid for this member's public key") from exc
