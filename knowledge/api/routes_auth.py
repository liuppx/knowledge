from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from knowledge.core.settings import get_settings
from knowledge.db.session import get_db
from knowledge.models import (
    EvidenceUnit,
    ImportedChunk,
    ImportedDocument,
    KBRelease,
    KBReleaseItem,
    KnowledgeBase,
    KnowledgeItem,
    KnowledgeItemEvidenceLink,
    KnowledgeItemRevision,
    Source,
    SourceAsset,
    WalletUser,
)
from knowledge.schemas.auth import ChallengeRequest, ChallengeResponse, PassportSessionResponse, PassportStatusResponse, RefreshRequest, TokenResponse, VerifyRequest
from knowledge.services.auth import AuthService
from knowledge.services.passport_auth import PassportAuthService
from knowledge.utils.time import utc_now


router = APIRouter(prefix="/auth", tags=["auth"])
service = AuthService()
passport_service = PassportAuthService()
settings = get_settings()
DEMO_WALLET_ADDRESS = "0x000000000000000000000000000000000000de00"
DEMO_KB_NAME = "Demo Knowledge Workspace"
DEMO_DOCUMENT_PATH = "/apps/knowledge.yeying.pub/uploads/demo-knowledge-operating-system.md"
DEMO_RELEASE_VERSION = "demo-v1"


def _demo_kb_config() -> dict:
    return {
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "retrieval_top_k": settings.retrieval_top_k,
        "memory_top_k": settings.memory_top_k,
        "embedding_model": settings.embedding_model,
    }


def _ensure_demo_content(db: Session) -> None:
    kb = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.owner_wallet_address == DEMO_WALLET_ADDRESS)
        .filter(KnowledgeBase.name == DEMO_KB_NAME)
        .first()
    )
    if kb is None:
        kb = KnowledgeBase(
            owner_wallet_address=DEMO_WALLET_ADDRESS,
            name=DEMO_KB_NAME,
            description="用于快速体验 knowledge 的示例知识库。它展示从原始材料到可审计知识资产的基本结构。",
            retrieval_config=_demo_kb_config(),
        )
        db.add(kb)
        db.flush()

    document = (
        db.query(ImportedDocument)
        .filter(ImportedDocument.kb_id == kb.id)
        .filter(ImportedDocument.source_path == DEMO_DOCUMENT_PATH)
        .first()
    )
    if document is None:
        document = ImportedDocument(
            kb_id=kb.id,
            owner_wallet_address=DEMO_WALLET_ADDRESS,
            source_path=DEMO_DOCUMENT_PATH,
            source_file_name="demo-knowledge-operating-system.md",
            source_kind="warehouse",
            source_etag_or_mtime="demo-v1",
            parse_status="succeeded",
            chunk_count=0,
            last_indexed_at=utc_now(),
        )
        db.add(document)
        db.flush()

    existing_chunks = (
        db.query(ImportedChunk)
        .filter(ImportedChunk.document_id == document.id)
        .count()
    )
    if existing_chunks == 0:
        chunks = [
            "knowledge 的产品目标是把原始文件、会议记录、设计讨论和人工输入整理为可维护的 Markdown 原生知识资产。",
            "系统主链路包括 Source、Asset、Evidence、Candidate、Knowledge Item、Release 和 Service Search，适合做可审计知识运营。",
            "面向 Agent 的关键价值不是简单问答，而是持续整理、版本化发布、保留证据来源，并向外部智能体提供稳定检索面。",
            "下一阶段产品体验应该优先降低首次试用门槛：Demo 登录、示例资产、导入任务、文档切片和检索验证需要形成闭环。",
        ]
        for index, text in enumerate(chunks):
            db.add(
                ImportedChunk(
                    document_id=document.id,
                    kb_id=kb.id,
                    owner_wallet_address=DEMO_WALLET_ADDRESS,
                    chunk_index=index,
                    text=text,
                    metadata_json={"demo": True, "section": "product_walkthrough", "source": "auth/demo"},
                )
            )
        document.chunk_count = len(chunks)
        document.parse_status = "succeeded"
        document.last_indexed_at = utc_now()
    elif document.chunk_count != existing_chunks:
        document.chunk_count = int(existing_chunks)

    source = (
        db.query(Source)
        .filter(Source.kb_id == kb.id)
        .filter(Source.source_path == "/apps/knowledge.yeying.pub/uploads")
        .first()
    )
    if source is None:
        source = Source(
            kb_id=kb.id,
            source_type="warehouse",
            source_path="/apps/knowledge.yeying.pub/uploads",
            scope_type="directory",
            enabled=True,
            sync_status="synced",
            last_seen_at=utc_now(),
            last_synced_at=utc_now(),
        )
        db.add(source)
        db.flush()

    asset = (
        db.query(SourceAsset)
        .filter(SourceAsset.source_id == source.id)
        .filter(SourceAsset.asset_path == DEMO_DOCUMENT_PATH)
        .first()
    )
    if asset is None:
        asset = SourceAsset(
            kb_id=kb.id,
            source_id=source.id,
            asset_path=DEMO_DOCUMENT_PATH,
            asset_name="demo-knowledge-operating-system.md",
            asset_type="markdown",
            source_version="demo-v1",
            availability_status="available",
            last_ingested_at=utc_now(),
        )
        db.add(asset)
        db.flush()

    chunks = (
        db.query(ImportedChunk)
        .filter(ImportedChunk.document_id == document.id)
        .order_by(ImportedChunk.chunk_index.asc())
        .all()
    )
    evidence_by_chunk = {
        int((evidence.source_locator or {}).get("chunk_index", -1)): evidence
        for evidence in db.query(EvidenceUnit).filter(EvidenceUnit.asset_id == asset.id).all()
    }
    for chunk in chunks:
        if chunk.chunk_index in evidence_by_chunk:
            continue
        db.add(
            EvidenceUnit(
                kb_id=kb.id,
                asset_id=asset.id,
                evidence_type="text_span",
                text=chunk.text,
                metadata_json={"demo": True, "document_id": document.id, "chunk_id": chunk.id},
                source_locator={"source_path": document.source_path, "chunk_index": chunk.chunk_index},
                vector_status="indexed",
            )
        )
    db.flush()

    evidence_units = (
        db.query(EvidenceUnit)
        .filter(EvidenceUnit.asset_id == asset.id)
        .order_by(EvidenceUnit.id.asc())
        .all()
    )
    if not evidence_units:
        return

    demo_items = [
        {
            "title": "knowledge 是面向 Agent 的版本化知识操作系统",
            "statement": "knowledge 的核心价值是把原始资产持续整理为可发布、可审计、可被 Agent 消费的专业知识，而不只是做一次性问答。",
            "item_type": "fact",
            "payload": {"fact": "knowledge turns raw assets into versioned, auditable, agent-ready knowledge."},
            "evidence_ids": [evidence_units[0].id, evidence_units[min(2, len(evidence_units) - 1)].id],
        },
        {
            "title": "Demo 首次试用路径",
            "statement": "首次试用应优先走 Demo 登录、示例资产、文档切片、正式知识项、发布和 Search Lab 检索验证的闭环。",
            "item_type": "procedure",
            "payload": {
                "steps": [
                    "点击一键进入 Demo",
                    "查看示例知识库和 Markdown 文档切片",
                    "在 Search Lab 搜索 Agent、versioning 或 knowledge",
                    "确认 formal/evidence 命中和审计信息",
                ]
            },
            "evidence_ids": [evidence_units[-1].id],
        },
    ]

    release_pairs: list[tuple[KnowledgeItem, KnowledgeItemRevision]] = []
    for item_payload in demo_items:
        revision = (
            db.query(KnowledgeItemRevision)
            .join(KnowledgeItem, KnowledgeItem.id == KnowledgeItemRevision.knowledge_item_id)
            .filter(KnowledgeItem.kb_id == kb.id)
            .filter(KnowledgeItemRevision.title == item_payload["title"])
            .first()
        )
        if revision is None:
            item = KnowledgeItem(
                kb_id=kb.id,
                item_type=item_payload["item_type"],
                origin_type="manual",
                lifecycle_status="confirmed",
                is_hotfix=False,
            )
            db.add(item)
            db.flush()
            revision = KnowledgeItemRevision(
                knowledge_item_id=item.id,
                revision_no=1,
                title=item_payload["title"],
                statement=item_payload["statement"],
                structured_payload_json=item_payload["payload"],
                item_contract_version="v1",
                review_status="accepted",
                visibility_status="active",
                created_by=DEMO_WALLET_ADDRESS,
                reviewed_by=DEMO_WALLET_ADDRESS,
                provenance_type="demo_seed",
                provenance_json={"created_via": "auth/demo", "demo": True},
                source_note="Demo seed content generated from the sample Markdown document.",
                applicability_scope_json={"demo": True},
                is_workspace_head=True,
            )
            db.add(revision)
            db.flush()
            item.current_revision_id = revision.id
            for rank, evidence_id in enumerate(item_payload["evidence_ids"], start=1):
                db.add(
                    KnowledgeItemEvidenceLink(
                        knowledge_item_revision_id=revision.id,
                        evidence_unit_id=evidence_id,
                        role="supporting",
                        rank=rank,
                        summary=item_payload["statement"][:255],
                    )
                )
            db.flush()
        item = db.get(KnowledgeItem, revision.knowledge_item_id)
        if item is not None:
            item.current_revision_id = revision.id
            item.lifecycle_status = "confirmed"
            release_pairs.append((item, revision))

    release = (
        db.query(KBRelease)
        .filter(KBRelease.kb_id == kb.id)
        .filter(KBRelease.version == DEMO_RELEASE_VERSION)
        .first()
    )
    if release is None and release_pairs:
        release = KBRelease(
            kb_id=kb.id,
            version=DEMO_RELEASE_VERSION,
            status="published",
            release_note="Demo release for first-run Search Lab validation.",
            published_at=utc_now(),
            created_by=DEMO_WALLET_ADDRESS,
        )
        db.add(release)
        db.flush()
    if release is not None:
        release.status = "published"
        existing_release_revision_ids = {
            item.knowledge_item_revision_id
            for item in db.query(KBReleaseItem).filter(KBReleaseItem.release_id == release.id).all()
        }
        for item, revision in release_pairs:
            if revision.id in existing_release_revision_ids:
                continue
            db.add(
                KBReleaseItem(
                    release_id=release.id,
                    knowledge_item_id=item.id,
                    knowledge_item_revision_id=revision.id,
                    item_version_hash=f"demo-v1-{revision.id}",
                    content_health_status="healthy",
                )
            )


@router.post("/challenge", response_model=ChallengeResponse)
def create_challenge(payload: ChallengeRequest, request: Request, db: Session = Depends(get_db)) -> ChallengeResponse:
    configured_domain = service.settings.siwe_domain.strip()
    configured_uri = service.settings.siwe_uri.strip()
    if service.settings.app_env != "development" and (not configured_domain or not configured_uri):
        raise HTTPException(status_code=503, detail="SIWE_DOMAIN and SIWE_URI must be configured outside development")
    request_origin = f"{request.url.scheme}://{request.url.netloc}"
    try:
        challenge = service.create_challenge(
            db,
            payload.wallet_address,
            domain=configured_domain or request.url.netloc,
            uri=configured_uri or request_origin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChallengeResponse(
        wallet_address=challenge.wallet_address,
        nonce=challenge.nonce,
        message=challenge.message,
        challenge=challenge.message,
        expires_at=challenge.expires_at,
    )


@router.post("/verify", response_model=TokenResponse)
def verify_signature(payload: VerifyRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = service.verify_signature(db, payload.wallet_address, payload.signature)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    access, refresh = service.create_token_pair(user.wallet_address)
    return TokenResponse(
        access_token=access[0],
        token=access[0],
        refresh_token=refresh[0],
        wallet_address=user.wallet_address,
        expires_at=access[1],
        refresh_expires_at=refresh[1],
    )


@router.post("/passport/sessions", response_model=PassportSessionResponse)
def create_passport_session(db: Session = Depends(get_db)) -> PassportSessionResponse:
    try:
        session = passport_service.create_session(db)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return PassportSessionResponse(session_id=session.id, verify_url=session.verify_url, status=session.status, expires_at=session.expires_at)


@router.get("/passport/callback", response_class=HTMLResponse)
def passport_callback(code: str = Query(min_length=1), state: str = Query(min_length=1), db: Session = Depends(get_db)) -> HTMLResponse:
    try:
        passport_service.receive_callback(db, state, code)
    except LookupError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return HTMLResponse("<html><body><p>夜莺通行证登录已确认，请回到 Knowledge 继续使用。</p></body></html>")


@router.get("/passport/sessions/{session_id}", response_model=PassportStatusResponse)
def get_passport_session(session_id: str, db: Session = Depends(get_db)) -> PassportStatusResponse:
    try:
        session = passport_service.complete_session(db, session_id)
    except LookupError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if session.status != "completed" or not session.wallet_address:
        return PassportStatusResponse(status=session.status)
    access, refresh = service.create_token_pair(session.wallet_address)
    return PassportStatusResponse(
        status="completed",
        token=TokenResponse(
            access_token=access[0], token=access[0], refresh_token=refresh[0], wallet_address=session.wallet_address,
            expires_at=access[1], refresh_expires_at=refresh[1],
        ),
    )


@router.post("/demo", response_model=TokenResponse)
def demo_login(db: Session = Depends(get_db)) -> TokenResponse:
    if settings.app_env != "development" and not settings.debug:
        raise HTTPException(status_code=403, detail="demo login is only available in development")
    user = db.get(WalletUser, DEMO_WALLET_ADDRESS)
    if user is None:
        user = WalletUser(wallet_address=DEMO_WALLET_ADDRESS)
        db.add(user)
    user.last_login_at = utc_now()
    _ensure_demo_content(db)
    db.commit()
    access, refresh = service.create_token_pair(DEMO_WALLET_ADDRESS)
    return TokenResponse(
        access_token=access[0],
        refresh_token=refresh[0],
        wallet_address=DEMO_WALLET_ADDRESS,
        expires_at=access[1],
        refresh_expires_at=refresh[1],
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshRequest) -> TokenResponse:
    try:
        claims = service.parse_token(payload.refresh_token, expected_type="refresh")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    access, refresh = service.create_token_pair(str(claims["wallet_address"]).lower())
    return TokenResponse(
        access_token=access[0],
        refresh_token=refresh[0],
        wallet_address=str(claims["wallet_address"]).lower(),
        expires_at=access[1],
        refresh_expires_at=refresh[1],
    )


@router.post("/logout")
def logout() -> dict:
    return {"ok": True}
