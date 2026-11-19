"""知行图知识操作的编码与签名校验:与链上节点逐字节一致。

向量由知行图节点的命令行生成(种子 07…07,与任何真实成员无关):

    node keygen --seed 0707…07 --out k.seed
    node encode-knowledge-op --key-file k.seed --actor 5 --nonce 3 --action create --layer explanation --domain 2 \\
        --body zh:11…11 --body en:22…22 --source model-verified:claude-opus-5-5 --cite 8:2:basis --cite 9:1:see-also
    node encode-knowledge-op --key-file k.seed --actor 5 --nonce 4 --action publish --unit 12 \\
        --body zh:33…33 --source human --cite 7:1:supersedes

ed25519 签名是确定性的,所以整段 op ‖ 签名都能逐字节比较。
"""

from __future__ import annotations

import pytest

from knowledge.services.kdg_codec import KdgCodecError, encode_action, encode_op, verify_signed_op

PUBKEY = "ea4a6c63e29c520abef5507b132ec5f9954776aebebe7b92421eea691446d22c"
CREATE = {
    "type": "create", "layer": "explanation", "domain": 2,
    "bodies": [{"lang": "zh", "hash": "11" * 32}, {"lang": "en", "hash": "22" * 32}],
    "source": {"type": "model-verified", "id": "claude-opus-5-5"},
    "cites": [{"unit": 8, "version": 2, "kind": "basis"}, {"unit": 9, "version": 1, "kind": "see-also"}],
}
PUBLISH = {
    "type": "publish", "unit": 12, "bodies": [{"lang": "zh", "hash": "33" * 32}],
    "source": {"type": "human"}, "cites": [{"unit": 7, "version": 1, "kind": "supersedes"}],
}
CREATE_SIGNED = "00000000000000050001000000020000000000000002000000027a68111111111111111111111111111111111111111111111111111111111111111100000002656e2222222222222222222222222222222222222222222222222222222222222222020000000f636c617564652d6f7075732d352d350000000000000002000000000000000800000002000000000000000009000000010100000000000000034e703d5071949e40f35c94ed490a4668eb59cec69aeb4b55b167039ec730d6b62d88e9f524bf2e0b8b721bc47a40009142d534f39a225628b15de2136667330a"
PUBLISH_SIGNED = "000000000000000501000000000000000c0000000000000001000000027a68333333333333333333333333333333333333333333333333333333333333333300000000000000000100000000000000070000000102000000000000000488e58e103a89a05f94b8013fe9fcd764f81ce24c195fed65319c237bbfbfb4518be81460b0731a8df179b2e2bdd55b7c7d5e520489462ff23b92b1a5c20b420f"


@pytest.mark.parametrize("signed_hex,action,nonce", [(CREATE_SIGNED, CREATE, 3), (PUBLISH_SIGNED, PUBLISH, 4)])
def test_encoding_matches_the_chain_node_byte_for_byte(signed_hex: str, action: dict, nonce: int) -> None:
    signed = bytes.fromhex(signed_hex)
    assert signed[:-64] == encode_op(5, action, nonce)
    verify_signed_op(signed, actor=5, action=action, nonce=nonce, pubkey_hex=PUBKEY)


def test_tampering_is_rejected() -> None:
    signed = bytes.fromhex(CREATE_SIGNED)
    with pytest.raises(KdgCodecError, match="does not match"):
        verify_signed_op(signed, actor=5, action={**CREATE, "domain": 1}, nonce=3, pubkey_hex=PUBKEY)
    with pytest.raises(KdgCodecError, match="does not match"):
        verify_signed_op(signed, actor=6, action=CREATE, nonce=3, pubkey_hex=PUBKEY)
    with pytest.raises(KdgCodecError, match="not valid"):
        verify_signed_op(signed, actor=5, action=CREATE, nonce=3, pubkey_hex="ab" * 32)
    broken = bytearray(signed)
    broken[-1] ^= 1
    with pytest.raises(KdgCodecError, match="not valid"):
        verify_signed_op(bytes(broken), actor=5, action=CREATE, nonce=3, pubkey_hex=PUBKEY)


def test_invalid_intents_are_rejected_before_anything_is_uploaded() -> None:
    with pytest.raises(KdgCodecError):
        encode_action({**CREATE, "layer": "theory"})
    with pytest.raises(KdgCodecError):
        encode_action({**CREATE, "source": {"type": "model", "id": "x" * 65}})
    with pytest.raises(KdgCodecError):
        encode_action({**CREATE, "cites": [{"unit": 1, "version": 1, "kind": "depends"}]})
    with pytest.raises(KdgCodecError):
        encode_action({**CREATE, "bodies": [{"lang": "中文中文中文", "hash": "11" * 32}]})
    with pytest.raises(KdgCodecError):
        encode_action({"type": "delete"})
