from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class KdgGeneratedBy(BaseModel):
    """修订的模型来源:model 为空表示人工撰写;human_edited 表示模型生成后经人工修改核对。"""

    model: str = Field(default="", max_length=64)
    human_edited: bool = False


class KdgSettingsUpdateRequest(BaseModel):
    domain: Optional[int] = Field(default=None, description="知行图领域编号(链的创世参数,见 /id/domain)")
    layer: Optional[Literal["foundation", "explanation", "scenario", "application"]] = None
    language: Optional[str] = Field(default=None, description="当前修订正文的语言,如 zh、en")
    generated_by: Optional[KdgGeneratedBy] = None


class KdgRelationCreateRequest(BaseModel):
    to_item_id: int
    kind: Literal["basis", "see-also", "supersedes"] = "basis"


class KdgRelationRead(BaseModel):
    id: int
    to_item_id: int
    kind: str
    to_chain_unit: Optional[int] = None


class KdgPublicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    revision_id: int
    network: str
    status: str
    op_type: str
    chain_unit: Optional[int] = None
    chain_version: Optional[int] = None
    body_sha256: str
    body_url: str
    op_hash: str
    actor: Optional[int] = None
    actor_pubkey: str
    error: str
    created_at: datetime
    updated_at: datetime


class KdgDomain(BaseModel):
    id: int
    name_zh: str
    name_en: str


class KdgStatusResponse(BaseModel):
    enabled: bool
    domains: list[KdgDomain] = Field(default_factory=list)
    network: str
    domain: Optional[int] = None
    layer: Optional[str] = None
    chain_unit: Optional[int] = None
    chain_version: Optional[int] = None
    unit_url: Optional[str] = None
    current_revision_published: bool
    pending: Optional[KdgPublicationRead] = None
    relations: list[KdgRelationRead]
    publications: list[KdgPublicationRead]


class KdgPrepareRequest(BaseModel):
    pubkey: str = Field(description="钱包里知行图账户的公钥(zhixing_requestAccounts 返回),64 位十六进制")


class KdgIntent(BaseModel):
    """交给钱包签名的意图(zhixing_signKnowledgeOp 的参数):谁、第几条、做什么。"""

    actor: str
    nonce: str
    action: dict


class KdgPrepareResponse(BaseModel):
    publication: KdgPublicationRead
    intent: KdgIntent
    body_markdown: str


class KdgSubmitRequest(BaseModel):
    signed: str = Field(description="钱包返回的 signed:op ‖ 签名 的十六进制")
    address: str = Field(description="钱包返回的 address:签名所用的知行图公钥")
