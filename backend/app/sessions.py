import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .db import get_db
from .ml import FEATURE_LABELS, get_predictor, judge_stage
from .models import Purchase, ShoppingSession, View, utc_now

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    # 결제 없이 새로 시작할 때 닫을 이전 세션
    previous_session_id: str | None = None
    # experience: 사람이 한 체험 / simulated: 가상 손님 스크립트
    # 재학습 데이터에는 experience만 쓴다. 프론트는 보내지 않아도 된다.
    mode: Literal["experience", "simulated"] = "experience"


class ItemRequest(BaseModel):
    item_id: str


def now_ms():
    return int(time.time() * 1000)


def get_session(db: Session, session_id: str) -> ShoppingSession:
    session = db.get(ShoppingSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return session


def get_active_session(db: Session, session_id: str) -> ShoppingSession:
    session = get_session(db, session_id)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="이미 끝난 세션입니다.")
    return session


def load_views(db: Session, session_id: str):
    # 이 세션의 조회만 모델 입력으로 쓴다. 결제 기록은 넣지 않는다.
    rows = db.exec(
        select(View).where(View.session_id == session_id).order_by(View.id)
    ).all()
    return [(row.timestamp, row.item_id) for row in rows]


@router.post("")
def create_session(request: CreateSessionRequest, db: Session = Depends(get_db)):
    if request.previous_session_id:
        previous = db.get(ShoppingSession, request.previous_session_id)
        if previous is not None and previous.status == "active":
            previous.status = "abandoned"
            previous.ended_at = utc_now()
            db.add(previous)

    session = ShoppingSession(model_version=get_predictor().version, mode=request.mode)
    db.add(session)
    db.commit()

    return {"session_id": session.id}


@router.post("/{session_id}/views")
def add_view(session_id: str, request: ItemRequest, db: Session = Depends(get_db)):
    get_active_session(db, session_id)

    view = View(session_id=session_id, item_id=request.item_id, timestamp=now_ms())
    db.add(view)
    db.flush()

    views = load_views(db, session_id)
    predictor = get_predictor()
    stage = judge_stage(predictor.timeline(views), predictor.base_probability)
    view.stage = stage["stage"]
    db.add(view)
    db.commit()

    return {
        "prediction": predictor.predict(views),
        # metrics는 기준값 조정용이라 화면에는 보내지 않는다.
        "stage": {"stage": stage["stage"], "items": stage["items"]},
    }


@router.post("/{session_id}/purchases")
def add_purchase(
    session_id: str, request: ItemRequest, db: Session = Depends(get_db)
):
    session = get_active_session(db, session_id)

    purchase = Purchase(
        session_id=session_id, item_id=request.item_id, timestamp=now_ms()
    )
    session.status = "purchased"
    session.ended_at = utc_now()
    db.add(purchase)
    db.add(session)
    db.commit()

    return {"session_id": session_id, "item_id": purchase.item_id, "status": session.status}


def views_before_decision(views, purchased_item):
    """결제하러 들어간 마지막 방문(마지막 구매 상품 조회 1개)을 뺀 조회 목록.

    구매하려면 상품 상세페이지를 거쳐야 해서, 구매 상품은 항상 마지막 조회가 된다.
    이 조회까지 넣으면 "방금 본 상품"이라는 이유만으로 맞히게 되므로 채점에서 뺀다.
    그보다 앞에서 본 구매 상품 조회는 바로 앞에 연달아 있어도 결정 전부터의 관심이라 남긴다.
    (상세페이지에 한 번 들어갈 때 조회는 한 번만 기록되므로, 연속 조회는 실제로 다시 본 것이다)
    """
    if views and views[-1][1] == purchased_item:
        return views[:-1]
    return views


@router.get("/{session_id}/predictions")
def get_predictions(session_id: str, db: Session = Depends(get_db)):
    get_session(db, session_id)

    views = load_views(db, session_id)
    if not views:
        raise HTTPException(status_code=400, detail="조회 기록이 없습니다.")

    purchase = db.exec(
        select(Purchase).where(Purchase.session_id == session_id).order_by(Purchase.id)
    ).first()
    purchased_item = purchase.item_id if purchase else None
    scored_views = views_before_decision(views, purchased_item) if purchase else views

    predictor = get_predictor()
    return {
        # 결제하러 들어간 마지막 방문 직전 기준의 예측. 남는 조회가 없으면 null
        "prediction": predictor.predict(scored_views) if scored_views else None,
        "purchased_item": purchased_item,
        "excluded_views": len(views) - len(scored_views),
        # 확률 변화는 결제 직전까지 전체를 보여준다
        "timeline": predictor.timeline(views),
        "feature_labels": FEATURE_LABELS,
    }
