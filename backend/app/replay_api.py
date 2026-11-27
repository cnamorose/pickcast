"""판매자 대시보드 재생 API (시뮬레이션 화면).

ml 쪽에서 미리 만든 하루치 재생 파일(ml/results/replay/날짜.json, build_replay.py)을 내준다.
학습에 쓰지 않은 test 기간(2015년 8~9월) 하루를 1분 간격으로 계산한 대시보드 상태와 실제 기록이다.
요청마다 파일을 읽어 재시작 없이 바뀐다.

- /replay/days: 재생할 수 있는 날짜 목록과 요약
- /replay/days/{date}: 하루치 재생 데이터. 1분마다 "그 뒤 10분 동안 실제로 팔린 수"를 붙인다.
  화면에서 다음 10분 예상 판매와 나란히 그린다.
"""
import json
import re
from bisect import bisect_right
from datetime import date as Date

from fastapi import APIRouter, HTTPException

from .ml import PROJECT_ROOT

router = APIRouter(prefix="/replay", tags=["replay"])

REPLAY_DIR = PROJECT_ROOT / "ml" / "results" / "replay"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WEEKDAYS = "월화수목금토일"
MISSING = "재생 파일이 없습니다. ml/product_purchase/build_replay.py를 먼저 실행하세요."


def weekday(day):
    return WEEKDAYS[Date.fromisoformat(day).weekday()]


def list_days(directory=REPLAY_DIR):
    days = []
    for path in sorted(directory.glob("*.json")):
        if not DATE_PATTERN.match(path.stem):
            continue
        replay = json.loads(path.read_text(encoding="utf-8"))
        days.append({
            "date": replay["date"],
            "weekday": weekday(replay["date"]),
            "version": replay["version"],
            **replay["summary"],
        })
    return days


def actual_next_window(purchase_seconds, minutes, horizon_minutes):
    """1분마다(시각 k분) (k분, k분 + horizon] 안에 산 구매 수."""
    seconds = sorted(purchase_seconds)
    window = horizon_minutes * 60
    return [
        bisect_right(seconds, k * 60 + window) - bisect_right(seconds, k * 60)
        for k in range(minutes)
    ]


def load_day(day, directory=REPLAY_DIR):
    if not DATE_PATTERN.match(day):
        raise HTTPException(status_code=400, detail="날짜는 YYYY-MM-DD 형식입니다.")
    path = directory / f"{day}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{day} {MISSING}")
    replay = json.loads(path.read_text(encoding="utf-8"))

    columns = replay["purchases"]["columns"]
    second, probability = columns.index("second"), columns.index("probability")
    rows = replay["purchases"]["rows"]
    minutes, horizon = replay["minutes"], replay["horizon_minutes"]
    return {
        **replay,
        "weekday": weekday(replay["date"]),
        # 모든 구매(사용자·상품별 첫 구매)
        "actual_next_10m": actual_next_window([r[second] for r in rows], minutes, horizon),
        # 그중 산 직전에 모델이 후보로 보고 있던 구매. 예상 판매와 같은 대상이다.
        "actual_known_next_10m": actual_next_window(
            [r[second] for r in rows if r[probability] is not None], minutes, horizon
        ),
    }


@router.get("/days")
def get_days():
    """재생할 수 있는 날짜와 요약 (고객, 기록, 구매, 10분 예상 합, 미리 본 구매, 1순위 적중)."""
    days = list_days()
    if not days:
        raise HTTPException(status_code=404, detail=MISSING)
    return {
        "days": days,
        "note": "학습에 쓰지 않은 2015년 8월 실제 기록입니다. 예측은 지금 쇼핑 중인 고객 기준입니다.",
    }


@router.get("/days/{day}")
def get_day(day: str):
    """하루치 재생 데이터: 1분마다 대시보드 상태, 실제 기록, 구매별 모델 순위, 다음 10분 실제 판매."""
    return load_day(day)
