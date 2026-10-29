from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from .db import get_db
from .inventory import STOCK
from .ml import compare_pairs, count_stages, forecast_sales, judge_stage, predictor
from .models import Purchase, ShoppingSession, View, utc_now
from .sessions import load_views, now_ms

router = APIRouter(tags=["dashboard"])

# 마지막 조회가 이 시간 안에 있는 active 세션을 "지금 쇼핑 중"으로 본다.
# 결제했거나 결제 없이 끝난 세션, 오래 방치된 세션을 넣으면 예상 구매 수가 계속 불어난다.
ACTIVE_WINDOW_MINUTES = 30
COMPARE_PAIRS_LIMIT = 10


def active_session_ids(db: Session):
    since = now_ms() - ACTIVE_WINDOW_MINUTES * 60_000
    last_view = (
        select(View.session_id, func.max(View.timestamp).label("last_viewed"))
        .group_by(View.session_id)
        .subquery()
    )
    return db.exec(
        select(ShoppingSession.id)
        .join(last_view, last_view.c.session_id == ShoppingSession.id)
        .where(ShoppingSession.status == "active", last_view.c.last_viewed >= since)
    ).all()


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    session_ids = active_session_ids(db)

    # 세션마다 마지막 조회 시점의 상품별 확률과 단계를 구해 상품별·단계별로 모은다.
    probabilities = defaultdict(list)
    stage_results = []
    for session_id in session_ids:
        views = load_views(db, session_id)
        for candidate in predictor.predict(views)["candidates"]:
            probabilities[candidate["item_id"]].append(candidate["probability"])
        stage_results.append(
            judge_stage(predictor.timeline(views), predictor.base_probability)
        )

    # 실제 결제 수는 쇼핑 중 세션이 아니라 전체 누적이다.
    purchased = dict(
        db.exec(
            select(Purchase.item_id, func.count()).group_by(Purchase.item_id)
        ).all()
    )

    # 아무도 안 본 상품도 0으로 넣어 표가 고객 수에 따라 줄었다 늘었다 하지 않게 한다.
    items = set(STOCK) | set(probabilities) | set(purchased)
    for item in items:
        probabilities.setdefault(item, [])
    products = [
        {**forecast, "purchased": purchased.get(forecast["item_id"], 0),
         "stock": STOCK.get(forecast["item_id"])}
        for forecast in forecast_sales(probabilities)
    ]
    # 1명 이상 살 확률이 상품 간 차이를 가장 잘 보여줘서 그 순서로 정렬한다.
    products.sort(key=lambda p: (-p["at_least_one"], -p["purchased"], p["item_id"]))

    return {
        "generated_at": utc_now().isoformat(),
        "active_sessions": len(session_ids),
        "active_window_minutes": ACTIVE_WINDOW_MINUTES,
        "products": products,
        "stages": count_stages(result["stage"] for result in stage_results),
        "compare_pairs": compare_pairs(stage_results, limit=COMPARE_PAIRS_LIMIT),
        # 규칙 기반 인사이트 문장은 다음 작업에서 채운다
        "insights": [],
    }
