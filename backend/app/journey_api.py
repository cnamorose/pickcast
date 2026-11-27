"""시뮬레이션 API: 같은 시간대 손님들의 쇼핑과 가게 전체 판매자 대시보드.

test 기간의 붐비는 두 시간(backend/app/data/journeys.json의 window)을 같은 시계로 재생한다.
모델(v3)은 이 기간 기록을 학습·보정에 쓰지 않았다.

- /journeys: 시간 창과, 화면 탭에 띄울 손님 목록·결과 요약 (scripts/build_journeys.py로 고른 손님)
- /journeys/store: 가게 전체 대시보드. 1분마다 쇼핑 중 손님, 다음 10분 예상 판매, 곧 팔릴 상품과
  가정 재고·알림, 팔린 상품 (store_simulation.py)
- /journeys/{id}: 손님 한 명의 행동마다 머문 시간과, 그 행동 직후 그 손님의 후보 상품별 구매 확률·순위·
  10분 안에 살 확률·주요 이유

시각은 모두 시간 창 시작부터의 초다. 손님의 예측은 이전 기록(history)까지 보고 계산한다.
시뮬레이션 화면은 서비스 버전(current.json)과 관계없이 조회·장바구니 입력 모델 v3를 쓴다.
"""
import json
import math
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from .ml import PROJECT_ROOT
from .replay_api import load_day
from .store_simulation import window_store

from horizon import load_rates, within_horizon  # noqa: E402  (ml/product_purchase)
from predict_extended import FEATURE_LABELS, ExtendedPredictor  # noqa: E402
from release import release_dir  # noqa: E402

router = APIRouter(prefix="/journeys", tags=["journeys"])

JOURNEYS_PATH = PROJECT_ROOT / "backend" / "app" / "data" / "journeys.json"
MODEL_VERSION = "v3"
TOUCH_EVENTS = ("view", "addtocart")
REASONS = 3
MISSING = "손님 기록이 없습니다. backend/scripts/build_journeys.py를 먼저 실행하세요."


@lru_cache(maxsize=1)
def model():
    directory = release_dir(MODEL_VERSION)
    return ExtendedPredictor(directory), load_rates(directory)


def reasons(candidate):
    """구매 확률에 가장 크게 기여한 피처 (SHAP 절댓값 순). 방향은 contribution 부호다."""
    contributions = sorted(candidate["shap"]["contributions"].items(), key=lambda kv: -abs(kv[1]))
    return [
        {
            "feature": name,
            "label": FEATURE_LABELS.get(name, name),
            # 값이 없는 피처(담은 적 없는 상품의 "마지막으로 담은 뒤 경과 시간" 등)는 NaN이라
            # JSON으로 보낼 수 없어 null로 바꾼다.
            "value": None if math.isnan(candidate["features"][name]) else candidate["features"][name],
            "contribution": round(value, 4),
        }
        for name, value in contributions[:REASONS]
    ]


def dashboard_at(events, second, predictor, rates):
    """second 시각(그 시각 기록 포함)까지의 기록으로 본 판매자 대시보드: 후보 상품과 산 상품."""
    touches = [(s * 1000, e, i) for s, e, i in events if e in TOUCH_EVENTS and s <= second]
    purchases = [(s * 1000, i) for s, e, i in events if e == "transaction" and s <= second]
    result = predictor.predict(touches, purchases)
    # 예측 모듈은 구매를 다음 조회·담기 때 반영하므로, 구매 직후에는 산 상품을 여기서 뺀다.
    purchased = list(dict.fromkeys([*result["purchased"], *(i for _, i in purchases)]))
    remaining = [c for c in result["candidates"] if c["item_id"] not in purchased]
    candidates = []
    for rank, c in enumerate(remaining, start=1):
        carted = c["features"]["cart_count"] > 0
        candidates.append({
            "item_id": c["item_id"],
            "probability": round(c["probability"], 4),
            "rank": rank,
            "decision": c["decision"],
            "carted": carted,
            # 방금 행동했으므로 마지막 행동 뒤 0분 기준
            "within_10m": round(float(within_horizon(c["probability"], 0.0, carted, rates)), 4),
            "reasons": reasons(c),
        })
    return {"candidates": candidates, "purchased": purchased}


def rank_at(step, item):
    match = next((c for c in step["dashboard"]["candidates"] if c["item_id"] == item), None)
    return (match["rank"], match["probability"]) if match else (None, None)


def purchase_outcomes(events, steps):
    """산 상품마다(같은 상품은 첫 구매만) 구매 전 대시보드에서 그 상품을 어떻게 봤는지.

    - rank_before, probability_before: 구매 바로 앞 행동 직후의 순위와 확률
    - rank_excluding_checkout: 바로 앞 행동이 산 상품을 보거나 담은 것(결제하러 들어간 행동)이면
      그 앞 행동 직후의 순위. 모델 평가의 "구매 직전 1순위"와 같은 기준이다.
    - top1_seconds_before: 구매 전 몇 초 동안 계속 1순위였는지 (1순위가 아니었으면 None)
    """
    outcomes = []
    seen = set()
    for index, (second, kind, item) in enumerate(events):
        if kind != "transaction" or item in seen:
            continue
        seen.add(item)
        before = [j for j in range(index) if events[j][1] in TOUCH_EVENTS and events[j][0] < second]
        rank, probability = rank_at(steps[before[-1]], item) if before else (None, None)

        checkout = before[:-1] if before and events[before[-1]][2] == item else before
        rank_excluding, _ = rank_at(steps[checkout[-1]], item) if checkout else (None, None)

        top1_since = None
        for j in reversed(before):
            if rank_at(steps[j], item)[0] != 1:
                break
            top1_since = events[j][0]
        outcomes.append({
            "item_id": item,
            "second": second,
            "rank_before": rank,
            "probability_before": probability,
            "rank_excluding_checkout": rank_excluding,
            "top1_seconds_before": None if top1_since is None else round(second - top1_since, 1),
        })
    return outcomes


@lru_cache(maxsize=4)
def load_journeys(path=JOURNEYS_PATH, modified=None):
    """손님 기록을 읽어 행동마다 대시보드를 계산한다. 파일이 바뀌면(modified) 다시 계산한다."""
    data = json.loads(path.read_text(encoding="utf-8"))
    predictor, rates = model()
    journeys = []
    for customer in data["customers"]:
        events = customer["events"]
        # 예측은 이전 기록(시각이 음수)까지 보고, 화면에는 이번 방문만 보여준다.
        everything = customer.get("history", []) + events
        steps = []
        for index, (second, kind, item) in enumerate(events):
            following = events[index + 1][0] if index + 1 < len(events) else None
            steps.append({
                "second": second,
                "event": kind,
                "item_id": item,
                # 다음 행동까지 걸린 시간 (마지막 행동은 없음)
                "dwell_seconds": None if following is None else round(following - second, 1),
                "dashboard": dashboard_at(everything, second, predictor, rates),
            })
        journeys.append({
            "id": customer["id"],
            "type": customer["type"],
            "label": customer["label"],
            "returning": bool(customer.get("history")),
            "steps": steps,
            "outcomes": purchase_outcomes(events, steps),
        })
    return {
        "source": data["source"],
        "window": data["window"],
        "version": predictor.version,
        "threshold": predictor.threshold,
        "journeys": journeys,
    }


def journeys(path=JOURNEYS_PATH):
    if not path.exists():
        raise HTTPException(status_code=404, detail=MISSING)
    return load_journeys(path, path.stat().st_mtime)


def summary(journey):
    outcomes = journey["outcomes"]
    return {
        "id": journey["id"],
        "type": journey["type"],
        "label": journey["label"],
        "returning": journey["returning"],
        "steps": len(journey["steps"]),
        "enter_second": journey["steps"][0]["second"],
        "leave_second": journey["steps"][-1]["second"],
        "bought": [o["item_id"] for o in outcomes],
        "ai_top1": sum(1 for o in outcomes if o["rank_before"] == 1),
    }


@router.get("")
def get_journeys():
    """시간 창과, 화면 탭에 띄울 손님 목록·결과 요약."""
    data = journeys()
    return {
        "version": data["version"],
        "source": data["source"],
        "window": data["window"],
        "customers": [summary(j) for j in data["journeys"]],
        "note": "학습에 쓰지 않은 2015년 8월 실제 쇼핑몰 기록입니다. 상품은 번호뿐이라 화면의 상품 이미지는 임의로 붙였습니다.",
    }


@router.get("/store")
def get_store():
    """가게 전체 대시보드: 시간 창의 1분마다 쇼핑 중 손님, 다음 10분 예상 판매, 곧 팔릴 상품과 가정 재고·알림."""
    window = journeys()["window"]
    day = load_day(window["date"])
    return {
        "window": window,
        **window_store(day, window["start_minute"], window["minutes"]),
        "note": "예측은 이미 들어와서 보거나 담은 손님 기준이라, 아직 들어오지 않은 손님의 구매는 예상에 없어요.",
    }


@router.get("/{journey_id}")
def get_journey(journey_id: int):
    """손님 한 명의 행동별 기록과 그 순간의 판매자 대시보드."""
    data = journeys()
    journey = next((j for j in data["journeys"] if j["id"] == journey_id), None)
    if journey is None:
        raise HTTPException(status_code=404, detail=f"{journey_id}번 손님이 없습니다.")
    return {"version": data["version"], "threshold": data["threshold"], "window": data["window"], **journey}
