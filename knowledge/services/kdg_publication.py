"""「上链到知行图」:把 Knowledge 的条目发布为知行图(KnowDoGraph)上的知识单元。

流程(字段对应见知行图仓库 docs/design/ontology-v0.1.md §8):

1. ``prepare``:校验 → 把当前修订渲染成 Markdown 正文、算哈希、上传到知行图正文仓库 → 查上链人的成员账户与
   序号 → 组好**意图** ``{actor, nonce, action}``。条目第一次上链用 ``create``(新单元),之后的修订用 ``publish``
   (同一单元的新版本)。
2. 浏览器请夜莺钱包对意图签名(``zhixing_signKnowledgeOp``),用户在钱包弹窗里确认。**服务端不接触私钥。**
3. ``submit``:核对签好的字节正是这条意图、签名对该成员公钥有效,再提交到链。
4. ``refresh``:按正文哈希查到它落在哪个单元的哪个版本,记为已上链。

不映射核验:Knowledge 的评审人目前就是作者本人,链上的核验必须由其他成员做。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from knowledge.adapters.kdg_chain import KdgChainError, KdgChainPort, build_kdg_chain
from knowledge.core.settings import get_settings
from knowledge.models import KdgPublication, KnowledgeItem, KnowledgeItemRelation, KnowledgeItemRevision
from knowledge.models.entities import KDG_ITEM_RELATION_KINDS
from knowledge.services.kdg_codec import KdgCodecError, encode_action, verify_signed_op
from knowledge.services.knowledge_items import KnowledgeItemsService

KDG_LAYERS = ("foundation", "explanation", "scenario", "application")
_PUBKEY_HEX = set("0123456789abcdef")


class KdgDisabledError(RuntimeError):
    """配置里没有开启知行图上链(KDG_MODE=disabled)。"""


@dataclass
class PreparedPublication:
    publication: KdgPublication
    intent: dict


def same_content(version: dict, sha: str, cites: list[dict]) -> bool:
    """链上某个版本与这次要发布的内容是否相同:正文哈希集合与引用(单元、版本、类型)都一致。"""
    bodies = {str(b.get("hash")) for b in version.get("bodies") or []}
    def norm(items: list[dict]) -> set[tuple[int, int, str]]:
        return {(int(c.get("unit", 0)), int(c.get("version", 0)), str(c.get("kind"))) for c in items or []}
    return bodies == {sha} and norm(version.get("cites") or []) == norm(cites)


def _is_pubkey(value: str) -> bool:
    v = str(value or "").lower()
    return len(v) == 64 and set(v) <= _PUBKEY_HEX


class KdgPublicationService:
    def __init__(self, items: KnowledgeItemsService | None = None, chain_factory=build_kdg_chain) -> None:
        self.items = items or KnowledgeItemsService()
        self._chain_factory = chain_factory

    # ---- 基础 -----------------------------------------------------------------------------
    def chain(self) -> KdgChainPort:
        chain = self._chain_factory()
        if chain is None:
            raise KdgDisabledError("知行图上链未开启(KDG_MODE=disabled)")
        return chain

    def enabled(self) -> bool:
        return self._chain_factory() is not None

    @staticmethod
    def render_markdown(item: KnowledgeItem, revision: KnowledgeItemRevision) -> str:
        """把修订渲染成知行图的正文(Markdown,第一行是标题)。输出确定:同样的修订总得到同样的哈希。"""
        payload = revision.structured_payload_json or {}
        lines = [f"# {revision.title.strip()}", "", revision.statement.strip(), ""]
        kind = item.item_type
        if kind == "fact" and payload.get("fact"):
            lines += ["## 事实", "", str(payload["fact"]).strip(), ""]
        elif kind == "rule" and payload.get("rule"):
            lines += ["## 规则", "", str(payload["rule"]).strip(), ""]
        elif kind == "procedure" and payload.get("steps"):
            lines += ["## 步骤", ""]
            for i, step in enumerate(payload["steps"], 1):
                text = step.get("text") or step.get("title") or json.dumps(step, ensure_ascii=False) if isinstance(step, dict) else step
                lines.append(f"{i}. {str(text).strip()}")
            lines.append("")
        elif kind == "faq":
            if payload.get("question"):
                lines += ["## 问题", "", str(payload["question"]).strip(), ""]
            if payload.get("answer"):
                lines += ["## 回答", "", str(payload["answer"]).strip(), ""]
        elif kind == "reference" and payload.get("reference_text"):
            lines += ["## 参考", "", str(payload["reference_text"]).strip(), ""]
        if revision.applicability_scope_json:
            lines += ["## 适用范围", "", "```json",
                      json.dumps(revision.applicability_scope_json, ensure_ascii=False, sort_keys=True, indent=2), "```", ""]
        if (revision.source_note or "").strip():
            lines += ["## 来源说明", "", revision.source_note.strip(), ""]
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def source_of(revision: KnowledgeItemRevision) -> dict:
        """来源:人工撰写 / 模型生成 / 模型生成且经人工修改核对。"""
        gen = revision.generated_by_json or {}
        model = str(gen.get("model") or "").strip()
        if not model:
            return {"type": "human"}
        return {"type": "model-verified" if gen.get("human_edited") else "model", "id": model}

    # ---- 查询 -----------------------------------------------------------------------------
    def _item(self, db: Session, wallet: str, kb_id: int, item_id: int) -> KnowledgeItem:
        return self.items.get_item_or_404(db, wallet, kb_id, item_id)

    def _publications(self, db: Session, item: KnowledgeItem) -> list[KdgPublication]:
        return list(db.scalars(
            select(KdgPublication)
            .join(KnowledgeItemRevision, KnowledgeItemRevision.id == KdgPublication.revision_id)
            .where(KnowledgeItemRevision.knowledge_item_id == item.id)
            .order_by(KdgPublication.id.asc())
        ).all())

    def chain_unit(self, db: Session, item: KnowledgeItem) -> tuple[int | None, int | None]:
        """条目在链上的单元号与最新已上链的版本号(还没上链则为 None)。"""
        confirmed = [p for p in self._publications(db, item) if p.status == "confirmed" and p.chain_unit]
        if not confirmed:
            return None, None
        last = confirmed[-1]
        return last.chain_unit, last.chain_version

    def relations(self, db: Session, item: KnowledgeItem) -> list[KnowledgeItemRelation]:
        return list(db.scalars(
            select(KnowledgeItemRelation).where(KnowledgeItemRelation.from_item_id == item.id)
            .order_by(KnowledgeItemRelation.id.asc())
        ).all())

    def status(self, db: Session, wallet: str, kb_id: int, item_id: int) -> dict:
        item = self._item(db, wallet, kb_id, item_id)
        unit, version = self.chain_unit(db, item)
        publications = self._publications(db, item)
        chain = self._chain_factory()
        domains: list[dict] = []
        if chain is not None:
            try:
                domains = chain.list_domains()
            except KdgChainError:
                domains = []  # 读不到领域列表时,前端退回到输入编号
        return {
            "enabled": chain is not None,
            "domains": domains,
            "network": get_settings().kdg_network,
            "domain": item.kdg_domain,
            "layer": item.kdg_layer,
            "chain_unit": unit,
            "chain_version": version,
            "unit_url": chain.unit_url(unit) if (chain is not None and unit) else None,
            "current_revision_published": any(
                p.status == "confirmed" and p.revision_id == item.current_revision_id for p in publications),
            "pending": next((p for p in reversed(publications) if p.status in ("prepared", "submitted")), None),
            "relations": [
                {"id": r.id, "to_item_id": r.to_item_id, "kind": r.kind,
                 "to_chain_unit": self.chain_unit(db, r.to_item)[0]}
                for r in self.relations(db, item)
            ],
            "publications": publications,
        }

    # ---- 设置 -----------------------------------------------------------------------------
    def update_settings(self, db: Session, wallet: str, kb_id: int, item_id: int, *, domain: int | None,
                        layer: str | None, language: str | None, generated_by: dict | None) -> None:
        item = self._item(db, wallet, kb_id, item_id)
        unit, _ = self.chain_unit(db, item)
        if unit and (domain != item.kdg_domain or layer != item.kdg_layer):
            raise ValueError("已经上链的条目不能再改领域或层级(链上单元的领域与层级不可改)")
        if layer is not None and layer not in KDG_LAYERS:
            raise ValueError("层级只能是 foundation / explanation / scenario / application")
        if domain is not None and domain <= 0:
            raise ValueError("领域编号应为正整数")
        item.kdg_domain = domain
        item.kdg_layer = layer
        revision = self.items.get_current_revision_or_404(db, item)
        if language is not None:
            lang = language.strip()
            if not lang or len(lang.encode("utf-8")) > 16:
                raise ValueError("语言标签应为 1–16 字节,例如 zh、en")
            revision.language = lang
        if generated_by is not None:
            model = str(generated_by.get("model") or "").strip()
            if len(model.encode("utf-8")) > 64:
                raise ValueError("模型标识最长 64 字节")
            revision.generated_by_json = {"model": model, "human_edited": bool(generated_by.get("human_edited"))} if model else {}
        db.commit()

    def add_relation(self, db: Session, wallet: str, kb_id: int, item_id: int, *, to_item_id: int, kind: str) -> KnowledgeItemRelation:
        item = self._item(db, wallet, kb_id, item_id)
        target = self._item(db, wallet, kb_id, to_item_id)
        if target.id == item.id:
            raise ValueError("不能引用自己")
        if kind not in KDG_ITEM_RELATION_KINDS:
            raise ValueError("引用类型只能是 basis / see-also / supersedes")
        exists = db.scalar(select(KnowledgeItemRelation).where(
            KnowledgeItemRelation.from_item_id == item.id, KnowledgeItemRelation.to_item_id == target.id,
            KnowledgeItemRelation.kind == kind))
        if exists is not None:
            return exists
        if len(self.relations(db, item)) >= 32:
            raise ValueError("一个条目最多 32 条引用(与链上限制一致)")
        relation = KnowledgeItemRelation(from_item_id=item.id, to_item_id=target.id, kind=kind, created_by=wallet)
        db.add(relation)
        db.commit()
        return relation

    def remove_relation(self, db: Session, wallet: str, kb_id: int, item_id: int, relation_id: int) -> None:
        item = self._item(db, wallet, kb_id, item_id)
        relation = db.get(KnowledgeItemRelation, relation_id)
        if relation is None or relation.from_item_id != item.id:
            raise LookupError("relation not found")
        db.delete(relation)
        db.commit()

    # ---- 上链 -----------------------------------------------------------------------------
    def prepare(self, db: Session, wallet: str, kb_id: int, item_id: int, *, pubkey: str) -> PreparedPublication:
        chain = self.chain()
        item = self._item(db, wallet, kb_id, item_id)
        revision = self.items.get_current_revision_or_404(db, item)
        pubkey = str(pubkey or "").lower()
        if not _is_pubkey(pubkey):
            raise ValueError("钱包返回的不是知行图公钥(应为 64 位十六进制)")
        if revision.review_status != "accepted":
            raise ValueError("只有已接受的修订才能上链")
        if not item.kdg_domain or not item.kdg_layer:
            raise ValueError("请先设置这个条目在知行图上的领域与层级")
        publications = self._publications(db, item)
        if any(p.status == "submitted" for p in publications):
            raise ValueError("上一次上链还在等待链上确认,请稍后刷新")
        if any(p.status == "confirmed" and p.revision_id == revision.id for p in publications):
            raise ValueError("当前修订已经上链;修改条目产生新修订后才能再次上链")
        # 旧的、没签名的准备记录作废(序号可能已经过期)
        for p in publications:
            if p.status == "prepared":
                p.status = "failed"
                p.error = "superseded by a newer prepare"

        try:
            member = chain.lookup_member(pubkey)
        except KdgChainError as exc:
            raise ValueError(str(exc)) from exc
        if member is None:
            raise ValueError("这个钱包里的知行图账户还不是测试网成员:请把公钥发给邀请你的成员")

        cites = []
        for relation in self.relations(db, item):
            target_unit, target_version = self.chain_unit(db, relation.to_item)
            if not target_unit:
                raise ValueError(f"被引用的条目 #{relation.to_item_id} 还没上链:请先把它上链")
            cites.append({"unit": target_unit, "version": target_version, "kind": relation.kind})

        body = self.render_markdown(item, revision).encode("utf-8")
        sha = hashlib.sha256(body).hexdigest()
        common = {"bodies": [{"lang": revision.language or "zh", "hash": sha}], "source": self.source_of(revision), "cites": cites}
        unit, _ = self.chain_unit(db, item)
        if unit:
            action = {"type": "publish", "unit": unit, **common}
        else:
            action = {"type": "create", "layer": item.kdg_layer, "domain": int(item.kdg_domain), **common}
        try:
            encode_action(action)  # 先在本地检查格式,有问题就不上传
        except KdgCodecError as exc:
            raise ValueError(f"内容不符合知行图的格式要求:{exc}") from exc

        try:
            existing = chain.lookup_body(sha)
        except KdgChainError as exc:
            raise ValueError(str(exc)) from exc
        if existing and (not unit or int(existing["unit"]) != int(unit)):
            raise ValueError(f"这份正文已经在知行图单元 #{existing['unit']} 里了(同一份正文只能属于一个单元);请修改内容后再上链")
        expected_version = 1
        if unit:
            try:
                versions = (chain.get_unit(unit) or {}).get("versions") or []
            except KdgChainError as exc:
                raise ValueError(str(exc)) from exc
            # 以链上最新版本为准(不只看本库的记录):正文与引用都没变,再发一版只会多一个一模一样的版本
            if versions and same_content(versions[-1], sha, cites):
                raise ValueError("这次修订渲染出的正文与引用都和链上最新版本相同,不需要再上链")
            expected_version = len(versions) + 1
        try:
            body_url = chain.put_body(sha, body)
            nonce = chain.get_nonce(member["account"])
        except KdgChainError as exc:
            raise ValueError(str(exc)) from exc

        intent = {"actor": str(member["account"]), "nonce": str(nonce), "action": action}
        publication = KdgPublication(
            revision_id=revision.id, kb_id=kb_id, network=get_settings().kdg_network, status="prepared",
            op_type=action["type"], chain_unit=unit, chain_version=expected_version, body_sha256=sha, body_url=body_url,
            actor=member["account"], actor_pubkey=pubkey, intent_json=intent, created_by=wallet,
        )
        db.add(publication)
        db.commit()
        return PreparedPublication(publication=publication, intent=intent)

    def submit(self, db: Session, wallet: str, kb_id: int, item_id: int, publication_id: int, *,
               signed_hex: str, address: str) -> KdgPublication:
        chain = self.chain()
        item = self._item(db, wallet, kb_id, item_id)
        publication = self._own_publication(db, item, publication_id)
        if publication.status != "prepared":
            raise ValueError(f"这条上链记录当前是「{publication.status}」,不能再提交")
        if str(address or "").lower() != publication.actor_pubkey:
            raise ValueError("签名的知行图账户与准备时的不一致:钱包里是否切换了账户?请重新上链")
        try:
            signed = bytes.fromhex(str(signed_hex or ""))
        except ValueError as exc:
            raise ValueError("签名结果不是十六进制") from exc
        intent = publication.intent_json
        try:
            verify_signed_op(signed, actor=int(intent["actor"]), action=intent["action"], nonce=int(intent["nonce"]),
                             pubkey_hex=publication.actor_pubkey)
        except KdgCodecError as exc:
            # 什么都没提交到链上:保持「已准备」,用户可以在钱包里重新签名
            raise ValueError(f"签名核对失败,没有提交:{exc}") from exc
        try:
            publication.op_hash = chain.submit_op(signed, intent=intent)
        except KdgChainError as exc:
            publication.status = "failed"
            publication.error = str(exc)
            db.commit()
            raise ValueError(str(exc)) from exc
        publication.status = "submitted"
        publication.error = ""
        db.commit()
        return self._try_confirm(db, chain, publication)

    def refresh(self, db: Session, wallet: str, kb_id: int, item_id: int, publication_id: int) -> KdgPublication:
        item = self._item(db, wallet, kb_id, item_id)
        publication = self._own_publication(db, item, publication_id)
        if publication.status != "submitted":
            return publication
        return self._try_confirm(db, self.chain(), publication)

    def _own_publication(self, db: Session, item: KnowledgeItem, publication_id: int) -> KdgPublication:
        publication = db.get(KdgPublication, publication_id)
        if publication is None or publication.revision.knowledge_item_id != item.id:
            raise LookupError("publication not found")
        return publication

    @staticmethod
    def _try_confirm(db: Session, chain: KdgChainPort, publication: KdgPublication) -> KdgPublication:
        """确认是否已上链。

        create:按正文哈希查它落在哪个单元(同一份正文只能属于一个单元)。
        publish:看这个单元的版本数是否已经够(版本数是链上的事实,不受正文是否与上一版相同的影响——
        修订只改了一句话、正文没变时,正文哈希与上一版相同,只能靠版本数区分)。
        """
        def is_ours(version: dict | None) -> bool:
            # 只认这位成员、用这份正文发布的版本:避免把别人(或更早)发布的同样正文误认为是这一次
            if not version:
                return False
            same_body = any(b.get("hash") == publication.body_sha256 for b in version.get("bodies") or [])
            return same_body and str(version.get("publisher")) == str(publication.actor)

        try:
            if publication.op_type == "publish":
                unit = chain.get_unit(publication.chain_unit) if publication.chain_unit else None
                versions = (unit or {}).get("versions") or []
                n = publication.chain_version or 0
                if len(versions) < n or not is_ours(versions[n - 1]):
                    return publication
            else:
                hit = chain.lookup_body(publication.body_sha256)
                if not hit:
                    return publication
                unit = chain.get_unit(hit["unit"]) or {}
                versions = unit.get("versions") or []
                if str(unit.get("author")) != str(publication.actor) or not versions or not is_ours(versions[0]):
                    return publication
                publication.chain_unit = int(hit["unit"])
                publication.chain_version = 1
        except KdgChainError:
            return publication
        publication.status = "confirmed"
        db.commit()
        return publication
