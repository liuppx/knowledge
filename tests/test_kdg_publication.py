"""「上链到知行图」的后端检验。

覆盖:
- Markdown 渲染:不同类型的条目按各自的契约渲染;同样的修订总得到同样的哈希;
- 来源判定:人工 / 模型生成 / 模型生成且经人工修改;
- prepare:校验(未设领域层级、修订未接受、不是成员)、组意图(create 还是 publish)、上传正文、记录序号;
- submit:核对签好的字节正是这条意图、签名对该成员公钥有效;签名不符、公钥不符、状态不对都拒绝;
- refresh:按正文哈希确认它落在哪个单元的哪个版本;
- 引用:只能引用已上链的条目;已上链的条目不能改领域与层级;
- 端到端(对着内存链):建条目 → 上链 → 再改出修订 → 再次上链 → 同一个单元出现 v2。

签名用知识仓库自己的 ed25519 实现(cryptography),公钥与签名与链上节点逐字节一致
(向量来自知行图节点的 encode-knowledge-op;另见 tests/test_kdg_codec.py)。
"""

from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from knowledge.adapters.kdg_chain import MockKdgChain, reset_mock_chain
from knowledge.main import app
from knowledge.services.kdg_codec import encode_op, verify_signed_op
from knowledge.services.kdg_publication import KdgPublicationService


def _login(client: TestClient, account) -> str:
    challenge = client.post("/auth/challenge", json={"wallet_address": account.address}).json()
    signed = Account.sign_message(encode_defunct(text=challenge["message"]), account.key)
    verify = client.post("/auth/verify", json={"wallet_address": account.address, "signature": signed.signature.hex()})
    verify.raise_for_status()
    return verify.json()["access_token"]


class Wallet:
    """知行图账户:一对 ed25519 密钥,以及用它给意图签名。"""

    def __init__(self) -> None:
        self.key = Ed25519PrivateKey.generate()
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.pubkey = raw.hex()

    def sign(self, intent: dict) -> str:
        op = encode_op(int(intent["actor"]), intent["action"], int(intent["nonce"]))
        sig = self.key.sign(b"zhixing-knowledge-op-v1" + op)
        return (op + sig).hex()


@pytest.fixture()
def kdg_chain(monkeypatch):
    chain = reset_mock_chain()
    monkeypatch.setenv("KDG_MODE", "mock")
    from knowledge.core import settings as settings_module

    settings_module.get_settings.cache_clear()
    monkeypatch.setenv("KNOWLEDGE_ENV_FILE", "/nonexistent")
    yield chain
    settings_module.get_settings.cache_clear()


@pytest.fixture()
def client(kdg_chain):
    with TestClient(app) as c:
        yield c


def _kb_and_item(client: TestClient, headers: dict[str, str], *, title: str = "渐进超负荷",
                 statement: str = "身体只会对超过它已经适应的负荷产生适应。", item_type: str = "fact",
                 payload: dict | None = None, kb_id: int | None = None) -> tuple[int, int]:
    if kb_id is None:
        kb_id = client.post("/kbs", headers=headers, json={"name": "KDG KB", "description": "kdg"}).json()["id"]
    created = client.post(f"/kbs/{kb_id}/items/manual", headers=headers, json={
        "title": title, "statement": statement, "item_type": item_type,
        "structured_payload_json": payload if payload is not None else {"fact": statement},
    })
    created.raise_for_status()
    return kb_id, created.json()["item"]["id"]


def test_markdown_rendering_is_deterministic_and_type_aware(kdg_chain: MockKdgChain) -> None:
    service = KdgPublicationService()

    class _Item:
        item_type = "fact"

    class _Revision:
        title = "渐进超负荷"
        statement = "身体只会对超过它已经适应的负荷产生适应。"
        structured_payload_json = {"fact": "负荷要逐步增加"}
        applicability_scope_json = {}
        source_note = ""
        language = "zh"

    body = service.render_markdown(_Item(), _Revision())
    assert body.startswith("# 渐进超负荷\n")
    assert "## 事实" in body and "负荷要逐步增加" in body
    assert body == service.render_markdown(_Item(), _Revision()), "同样的修订必须得到同样的正文(哈希才稳定)"

    class _Procedure(_Item):
        item_type = "procedure"

    class _Steps(_Revision):
        structured_payload_json = {"steps": ["先做 A", "再做 B"]}

    steps = service.render_markdown(_Procedure(), _Steps())
    assert "## 步骤" in steps and "1. 先做 A" in steps and "2. 再做 B" in steps

    class _Faq(_Item):
        item_type = "faq"

    class _FaqRev(_Revision):
        structured_payload_json = {"question": "为什么?", "answer": "因为…"}

    faq = service.render_markdown(_Faq(), _FaqRev())
    assert "## 问题" in faq and "## 回答" in faq


def test_source_is_derived_from_the_revision(kdg_chain: MockKdgChain) -> None:
    service = KdgPublicationService()

    class _Rev:
        generated_by_json: dict = {}

    assert service.source_of(_Rev()) == {"type": "human"}
    _Rev.generated_by_json = {"model": "claude-opus-5-5"}
    assert service.source_of(_Rev()) == {"type": "model", "id": "claude-opus-5-5"}
    _Rev.generated_by_json = {"model": "claude-opus-5-5", "human_edited": True}
    assert service.source_of(_Rev()) == {"type": "model-verified", "id": "claude-opus-5-5"}


def test_publish_flow_end_to_end(client: TestClient, kdg_chain: MockKdgChain) -> None:
    account = Account.create()
    token = _login(client, account)
    headers = {"Authorization": f"Bearer {token}"}
    kb_id, item_id = _kb_and_item(client, headers)

    # 未开启时状态接口可用,但没有链
    status = client.get(f"/kbs/{kb_id}/items/{item_id}/kdg", headers=headers).json()
    assert status["enabled"] is True and status["chain_unit"] is None

    # 没设领域与层级 → 拒绝
    wallet = Wallet()
    kdg_chain.add_member(wallet.pubkey)
    prepared = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey})
    assert prepared.status_code == 400
    assert "领域" in prepared.json()["detail"]

    # 设好之后可以准备:意图是 create,正文已上传
    settings = client.put(f"/kbs/{kb_id}/items/{item_id}/kdg/settings", headers=headers,
                          json={"domain": 2, "layer": "foundation", "language": "zh",
                                "generated_by": {"model": "claude-opus-5-5", "human_edited": False}})
    assert settings.status_code == 200
    prepared = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey})
    prepared.raise_for_status()
    data = prepared.json()
    assert data["intent"]["action"]["type"] == "create"
    assert data["intent"]["action"]["layer"] == "foundation"
    assert data["intent"]["action"]["domain"] == 2
    assert data["intent"]["action"]["source"] == {"type": "model", "id": "claude-opus-5-5"}
    assert data["intent"]["action"]["bodies"][0]["lang"] == "zh"
    assert data["intent"]["action"]["bodies"][0]["hash"] == hashlib.sha256(
        data["body_markdown"].encode("utf-8")).hexdigest()
    publication_id = data["publication"]["id"]
    assert data["publication"]["status"] == "prepared"

    # 签名不符:改了正文 → 拒绝,不提交
    tampered = dict(data["intent"])
    tampered["action"] = {**tampered["action"], "domain": 1}
    bad = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/publications/{publication_id}/submit", headers=headers,
                      json={"signed": wallet.sign(tampered), "address": wallet.pubkey})
    assert bad.status_code == 400
    assert "签名核对失败" in bad.json()["detail"]
    assert not kdg_chain.submitted

    # 公钥不符 → 拒绝
    other = Wallet()
    wrong = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/publications/{publication_id}/submit", headers=headers,
                        json={"signed": wallet.sign(data["intent"]), "address": other.pubkey})
    assert wrong.status_code == 400

    # 正确签名 → 提交并确认
    signed = wallet.sign(data["intent"])
    done = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/publications/{publication_id}/submit", headers=headers,
                       json={"signed": signed, "address": wallet.pubkey})
    done.raise_for_status()
    assert done.json()["status"] == "confirmed"
    assert done.json()["chain_unit"] == 1
    assert len(kdg_chain.submitted) == 1

    # 链上确实有这条单元
    unit = kdg_chain.get_unit(1)
    assert unit["layer"] == "foundation" and unit["domain"] == 2
    assert unit["versions"][0]["bodies"][0]["hash"] == data["publication"]["body_sha256"]

    # 已上链的条目不能改领域与层级
    locked = client.put(f"/kbs/{kb_id}/items/{item_id}/kdg/settings", headers=headers, json={"domain": 1, "layer": "application"})
    assert locked.status_code == 400

    # 改出修订 → 再上链 → 同一个单元的 v2(publish)
    updated = client.patch(f"/kbs/{kb_id}/items/{item_id}", headers=headers, json={
        "title": "渐进超负荷", "statement": "身体只会对超过它已经适应的负荷产生适应;加量的幅度决定进步快慢。"})
    updated.raise_for_status()
    second = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey})
    second.raise_for_status()
    assert second.json()["intent"]["action"]["type"] == "publish"
    assert second.json()["intent"]["action"]["unit"] == 1
    signed2 = wallet.sign(second.json()["intent"])
    done2 = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/publications/{second.json()['publication']['id']}/submit",
                        headers=headers, json={"signed": signed2, "address": wallet.pubkey})
    done2.raise_for_status()
    assert done2.json()["status"] == "confirmed"
    assert done2.json()["chain_unit"] == 1 and done2.json()["chain_version"] == 2
    assert len(kdg_chain.get_unit(1)["versions"]) == 2

    # 状态接口反映已上链
    status = client.get(f"/kbs/{kb_id}/items/{item_id}/kdg", headers=headers).json()
    assert status["chain_unit"] == 1 and status["chain_version"] == 2
    assert status["current_revision_published"] is True


def test_prepare_refuses_a_publisher_who_is_not_a_member(client: TestClient, kdg_chain: MockKdgChain) -> None:
    account = Account.create()
    headers = {"Authorization": f"Bearer {_login(client, account)}"}
    kb_id, item_id = _kb_and_item(client, headers)
    client.put(f"/kbs/{kb_id}/items/{item_id}/kdg/settings", headers=headers, json={"domain": 2, "layer": "foundation"})
    stranger = Wallet()
    response = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": stranger.pubkey})
    assert response.status_code == 400
    assert "成员" in response.json()["detail"]


def test_relations_must_point_at_published_items(client: TestClient, kdg_chain: MockKdgChain) -> None:
    account = Account.create()
    headers = {"Authorization": f"Bearer {_login(client, account)}"}
    kb_id, item_id = _kb_and_item(client, headers, title="深蹲", statement="依据渐进超负荷。", item_type="procedure",
                                  payload={"steps": ["站好", "下蹲"]})
    _, other_id = _kb_and_item(client, headers, title="另一个", statement="另一条。", kb_id=kb_id)

    # 跨知识库引用 → 找不到(只能引用同一知识库里的条目)
    other_kb, foreign_id = _kb_and_item(client, headers, title="别的库", statement="别的库里的一条。")
    assert client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/relations", headers=headers,
                       json={"to_item_id": foreign_id, "kind": "basis"}).status_code == 404
    client.put(f"/kbs/{kb_id}/items/{item_id}/kdg/settings", headers=headers, json={"domain": 2, "layer": "application"})
    client.put(f"/kbs/{kb_id}/items/{other_id}/kdg/settings", headers=headers, json={"domain": 2, "layer": "foundation"})

    # 引用还没上链的条目 → 准备时拒绝
    added = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/relations", headers=headers,
                        json={"to_item_id": other_id, "kind": "basis"})
    added.raise_for_status()
    wallet = Wallet()
    kdg_chain.add_member(wallet.pubkey)
    blocked = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey})
    assert blocked.status_code == 400
    assert "还没上链" in blocked.json()["detail"]

    # 先把被引用的条目上链,再准备就通过,并带上引用
    other_wallet = Wallet()
    kdg_chain.add_member(other_wallet.pubkey)
    prepared_other = client.post(f"/kbs/{kb_id}/items/{other_id}/kdg/prepare", headers=headers, json={"pubkey": other_wallet.pubkey})
    prepared_other.raise_for_status()
    confirmed_other = client.post(
        f"/kbs/{kb_id}/items/{other_id}/kdg/publications/{prepared_other.json()['publication']['id']}/submit",
        headers=headers, json={"signed": other_wallet.sign(prepared_other.json()["intent"]), "address": other_wallet.pubkey})
    confirmed_other.raise_for_status()
    other_unit = confirmed_other.json()["chain_unit"]
    prepared = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey})
    prepared.raise_for_status()
    cites = prepared.json()["intent"]["action"]["cites"]
    assert cites == [{"unit": other_unit, "version": 1, "kind": "basis"}]


def test_signed_op_verification_rejects_tampering(kdg_chain: MockKdgChain) -> None:
    wallet = Wallet()
    intent = {"actor": "1", "nonce": "0", "action": {"type": "verify", "unit": 8, "version": 2, "verdict": "pass"}}
    signed = bytes.fromhex(wallet.sign(intent))
    verify_signed_op(signed, actor=1, action=intent["action"], nonce=0, pubkey_hex=wallet.pubkey)
    with pytest.raises(Exception):
        verify_signed_op(signed, actor=1, action=intent["action"], nonce=1, pubkey_hex=wallet.pubkey)
    with pytest.raises(Exception):
        verify_signed_op(signed, actor=1, action=intent["action"], nonce=0, pubkey_hex="ab" * 32)


def test_unchanged_body_is_not_republished_and_publish_confirms_by_version(client: TestClient, kdg_chain: MockKdgChain) -> None:
    """修订没有改变正文时不再上链;publish 用版本数确认(正文相同时不能靠正文哈希区分版本)。"""
    account = Account.create()
    headers = {"Authorization": f"Bearer {_login(client, account)}"}
    kb_id, item_id = _kb_and_item(client, headers)
    client.put(f"/kbs/{kb_id}/items/{item_id}/kdg/settings", headers=headers, json={"domain": 2, "layer": "foundation"})
    wallet = Wallet()
    kdg_chain.add_member(wallet.pubkey)
    first = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey}).json()
    client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/publications/{first['publication']['id']}/submit", headers=headers,
                json={"signed": wallet.sign(first["intent"]), "address": wallet.pubkey}).raise_for_status()

    # 只改了来源说明以外的、不进正文的字段 → 新修订,但正文不变
    client.patch(f"/kbs/{kb_id}/items/{item_id}", headers=headers, json={"title": "渐进超负荷"}).raise_for_status()
    same = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey})
    assert same.status_code == 400
    assert "和链上最新版本相同" in same.json()["detail"]
    assert len(kdg_chain.get_unit(1)["versions"]) == 1

    # 以链上为准:新修订的正文已经由别处(例如更早的一次运行)发成了最新版本,本库没有记录 → 同样拒绝
    client.patch(f"/kbs/{kb_id}/items/{item_id}", headers=headers,
                 json={"statement": "身体只会对超过它已经适应的负荷产生适应;加量幅度决定进步快慢。"}).raise_for_status()
    probe = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey}).json()
    kdg_chain.submit_op(b"x", intent=probe["intent"])  # 同一份正文已成为 v2(没经过本库的 submit)
    again = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": wallet.pubkey})
    assert again.status_code == 400
    assert "和链上最新版本相同" in again.json()["detail"]
    assert len(kdg_chain.get_unit(1)["versions"]) == 2


def test_body_already_on_chain_is_refused_and_never_confirmed_against_someone_elses_unit(client: TestClient, kdg_chain: MockKdgChain) -> None:
    """链上已有同样的正文(别人发布的):准备时拒绝;即使提交了,也不会把别人的单元误认成自己的。"""
    account = Account.create()
    headers = {"Authorization": f"Bearer {_login(client, account)}"}
    kb_id, item_id = _kb_and_item(client, headers)
    client.put(f"/kbs/{kb_id}/items/{item_id}/kdg/settings", headers=headers, json={"domain": 2, "layer": "foundation"})
    me, someone = Wallet(), Wallet()
    kdg_chain.add_member(me.pubkey)
    other_account = kdg_chain.add_member(someone.pubkey)

    # 别人先用同样的正文建了单元
    from knowledge.models import KnowledgeItem  # noqa: F401  (确保模型已加载)
    body = KdgPublicationService.render_markdown(
        type("I", (), {"item_type": "fact"})(),
        type("R", (), {"title": "渐进超负荷", "statement": "身体只会对超过它已经适应的负荷产生适应。",
                       "structured_payload_json": {"fact": "身体只会对超过它已经适应的负荷产生适应。"},
                       "applicability_scope_json": {}, "source_note": ""})(),
    ).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    kdg_chain.put_body(sha, body)
    kdg_chain.submit_op(b"x", intent={"actor": other_account, "nonce": 0, "action": {
        "type": "create", "layer": "foundation", "domain": 2, "bodies": [{"lang": "zh", "hash": sha}],
        "source": {"type": "human"}, "cites": []}})

    refused = client.post(f"/kbs/{kb_id}/items/{item_id}/kdg/prepare", headers=headers, json={"pubkey": me.pubkey})
    assert refused.status_code == 400
    assert "已经在知行图单元 #1" in refused.json()["detail"]

    # 直接检查确认逻辑:就算有一条"已提交"的记录指向这份正文,也不会被确认成别人的单元
    from knowledge.models import KdgPublication

    publication = KdgPublication(revision_id=1, kb_id=kb_id, status="submitted", op_type="create",
                                 body_sha256=sha, actor=kdg_chain.lookup_member(me.pubkey)["account"],
                                 actor_pubkey=me.pubkey, intent_json={}, created_by="x")
    from knowledge.db.session import SessionLocal

    with SessionLocal() as db:
        db.add(publication)
        db.commit()
        result = KdgPublicationService._try_confirm(db, kdg_chain, publication)
        assert result.status == "submitted", "别人的单元不能算作这次上链"
        db.delete(publication)
        db.commit()
