import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from .db import get_db
from .ml import FEATURE_LABELS, MODEL_VERSION, judge_stage, predictor
from .models import Purchase, ShoppingSession, View, utc_now

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    # 결제 없이 새로 시작할 때 닫을 이전 세션
    previous_session_id: str | None = None


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

    session = ShoppingSession(model_version=MODEL_VERSION)
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


@router.get("/{session_id}/predictions")
def get_predictions(session_id: str, db: Session = Depends(get_db)):
    get_session(db, session_id)

    views = load_views(db, session_id)
    if not views:
        raise HTTPException(status_code=400, detail="조회 기록이 없습니다.")

    return {
        "prediction": predictor.predict(views),
        "timeline": predictor.timeline(views),
        "feature_labels": FEATURE_LABELS,
    }
