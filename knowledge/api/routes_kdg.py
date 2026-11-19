"""「上链到知行图」的接口。签名在浏览器里由夜莺钱包完成,这里只准备意图、核对签名、提交与查询状态。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from knowledge.api.deps import get_current_wallet
from knowledge.db.session import get_db
from knowledge.schemas.kdg import (
    KdgPrepareRequest,
    KdgPrepareResponse,
    KdgPublicationRead,
    KdgRelationCreateRequest,
    KdgSettingsUpdateRequest,
    KdgStatusResponse,
    KdgSubmitRequest,
)
from knowledge.services.kdg_publication import KdgDisabledError, KdgPublicationService


router = APIRouter(prefix="/kbs", tags=["kdg"])
kdg_service = KdgPublicationService()


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KdgDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _status(db: Session, wallet: str, kb_id: int, item_id: int) -> KdgStatusResponse:
    data = _call(kdg_service.status, db, wallet, kb_id, item_id)
    return KdgStatusResponse(
        **{k: v for k, v in data.items() if k not in ("pending", "publications")},
        pending=KdgPublicationRead.model_validate(data["pending"]) if data["pending"] else None,
        publications=[KdgPublicationRead.model_validate(p) for p in data["publications"]],
    )


@router.get("/{kb_id}/items/{item_id}/kdg", response_model=KdgStatusResponse)
def get_kdg_status(kb_id: int, item_id: int, wallet_address: str = Depends(get_current_wallet),
                   db: Session = Depends(get_db)) -> KdgStatusResponse:
    return _status(db, wallet_address, kb_id, item_id)


@router.put("/{kb_id}/items/{item_id}/kdg/settings", response_model=KdgStatusResponse)
def update_kdg_settings(kb_id: int, item_id: int, payload: KdgSettingsUpdateRequest,
                        wallet_address: str = Depends(get_current_wallet),
                        db: Session = Depends(get_db)) -> KdgStatusResponse:
    _call(kdg_service.update_settings, db, wallet_address, kb_id, item_id, domain=payload.domain, layer=payload.layer,
          language=payload.language,
          generated_by=payload.generated_by.model_dump() if payload.generated_by is not None else None)
    return _status(db, wallet_address, kb_id, item_id)


@router.post("/{kb_id}/items/{item_id}/kdg/relations", response_model=KdgStatusResponse)
def add_kdg_relation(kb_id: int, item_id: int, payload: KdgRelationCreateRequest,
                     wallet_address: str = Depends(get_current_wallet),
                     db: Session = Depends(get_db)) -> KdgStatusResponse:
    _call(kdg_service.add_relation, db, wallet_address, kb_id, item_id, to_item_id=payload.to_item_id, kind=payload.kind)
    return _status(db, wallet_address, kb_id, item_id)


@router.delete("/{kb_id}/items/{item_id}/kdg/relations/{relation_id}", response_model=KdgStatusResponse)
def remove_kdg_relation(kb_id: int, item_id: int, relation_id: int,
                        wallet_address: str = Depends(get_current_wallet),
                        db: Session = Depends(get_db)) -> KdgStatusResponse:
    _call(kdg_service.remove_relation, db, wallet_address, kb_id, item_id, relation_id)
    return _status(db, wallet_address, kb_id, item_id)


@router.post("/{kb_id}/items/{item_id}/kdg/prepare", response_model=KdgPrepareResponse)
def prepare_kdg_publication(kb_id: int, item_id: int, payload: KdgPrepareRequest,
                            wallet_address: str = Depends(get_current_wallet),
                            db: Session = Depends(get_db)) -> KdgPrepareResponse:
    prepared = _call(kdg_service.prepare, db, wallet_address, kb_id, item_id, pubkey=payload.pubkey)
    revision = prepared.publication.revision
    item = revision.knowledge_item
    return KdgPrepareResponse(
        publication=KdgPublicationRead.model_validate(prepared.publication),
        intent=prepared.intent,
        body_markdown=kdg_service.render_markdown(item, revision),
    )


@router.post("/{kb_id}/items/{item_id}/kdg/publications/{publication_id}/submit", response_model=KdgPublicationRead)
def submit_kdg_publication(kb_id: int, item_id: int, publication_id: int, payload: KdgSubmitRequest,
                           wallet_address: str = Depends(get_current_wallet),
                           db: Session = Depends(get_db)) -> KdgPublicationRead:
    publication = _call(kdg_service.submit, db, wallet_address, kb_id, item_id, publication_id,
                        signed_hex=payload.signed, address=payload.address)
    return KdgPublicationRead.model_validate(publication)


@router.post("/{kb_id}/items/{item_id}/kdg/publications/{publication_id}/refresh", response_model=KdgPublicationRead)
def refresh_kdg_publication(kb_id: int, item_id: int, publication_id: int,
                            wallet_address: str = Depends(get_current_wallet),
                            db: Session = Depends(get_db)) -> KdgPublicationRead:
    publication = _call(kdg_service.refresh, db, wallet_address, kb_id, item_id, publication_id)
    return KdgPublicationRead.model_validate(publication)
