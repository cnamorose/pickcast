"""시뮬레이션 화면(같은 시간대 손님들 + 가게 전체 대시보드)에 쓸 손님 기록을 원본에서 골라 저장한다.

모델(v3)이 학습·보정에 쓰지 않은 test 기간의 붐비는 두 시간(2015-08-17 17:00~19:00 UTC)을 재생한다.
그 시간에 실제로 쇼핑한 test 고객 중, 한 번의 방문(행동 사이 30분 이내, 행동 4~25개)이 시간 창 안에
모두 들어 있는 고객을 유형별로 고정 시드 무작위 2명씩 골라 화면 탭에 띄운다.
AI가 맞혔는지는 고른 뒤에 API가 계산한다 (잘 맞힌 손님만 고르지 않는다).

- compare_buy: 여러 상품(3개 이상)을 보고 담은 뒤 산 손님
- cart_leave: 담았지만 사지 않고 떠난 손님
- quick_buy: 몇 개(3개 이하)만 보고 15분 안에 산 손님

그 전에 온 적 있는 고객이면 test 기간의 이전 기록(history)도 넣는다. AI 예측은 이전 기록까지 보고
계산하고, 화면에는 이 방문(events)만 보여준다. 시각은 모두 시간 창 시작부터의 초다(이전 기록은 음수).

가게 전체 대시보드는 같은 날의 재생 파일(ml/results/replay/2015-08-17.json, ml build_replay.py)에서
이 시간 창만 잘라 쓴다.

원본 기록(ml/data/raw/events.csv)과 시간 분할 사용자 표(ml/data/product_purchase_time/users.parquet)가
있어야 한다. 결과(backend/app/data/journeys.json)는 Git에 올린다.

    python backend/scripts/build_journeys.py
"""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("PRODUCT_PURCHASE_DIR", "product_purchase_time")
sys.path.insert(0, str(PROJECT_ROOT / "ml" / "product_purchase"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from events import load_events, output_dir  # noqa: E402

OUTPUT = PROJECT_ROOT / "backend" / "app" / "data" / "journeys.json"
DATE = "2015-08-17"
START_HOUR = 17
WINDOW_MINUTES = 120
VISIT_GAP_MS = 30 * 60_000
MIN_EVENTS, MAX_EVENTS = 4, 25
PER_TYPE = 2
SEED = 7
TYPES = {
    "compare_buy": "여러 상품을 비교하다 산 손님",
    "cart_leave": "담고도 안 사고 떠난 손님",
    "quick_buy": "보자마자 산 손님",
}


def visit_type(visit):
    """한 번의 방문 기록(시간순 DataFrame)의 유형. 어느 유형도 아니면 None."""
    kinds = visit["event"].astype(str)
    touched = visit.loc[kinds != "transaction", "itemid"]
    bought = (kinds == "transaction").any()
    carted = (kinds == "addtocart").any()
    if kinds.iloc[0] != "view" or touched.empty:
        return None
    minutes = (visit["timestamp"].iloc[-1] - visit["timestamp"].iloc[0]) / 60_000
    if bought and carted and touched.nunique() >= 3:
        return "compare_buy"
    if carted and not bought:
        return "cart_leave"
    if bought and touched.nunique() <= 3 and minutes <= 15:
        return "quick_buy"
    return None


def window_visits(events, users, start, end):
    """시간 창 [start, end) 안에 모두 들어 있는 방문과 그 고객의 이전 기록.

    (고객, 유형, 방문 DataFrame, 이전 기록 DataFrame)을 낸다.
    """
    active = set(events.loc[(events["timestamp"] >= start) & (events["timestamp"] < end), "visitorid"]) & users
    mine = events[events["visitorid"].isin(active)].sort_values(["visitorid", "timestamp"], kind="stable")
    for uid, records in mine.groupby("visitorid", sort=True):
        times = records["timestamp"].to_numpy()
        cuts = np.flatnonzero(np.diff(times) > VISIT_GAP_MS) + 1
        for part in np.split(np.arange(len(records)), cuts):
            visit = records.iloc[part]
            first, last = visit["timestamp"].iloc[0], visit["timestamp"].iloc[-1]
            if first < start or last >= end or not MIN_EVENTS <= len(visit) <= MAX_EVENTS:
                continue
            kind = visit_type(visit)
            if kind:
                yield uid, kind, visit, records[records["timestamp"] < first]


def as_rows(frame, start):
    """[시간 창 시작부터 초, 종류(view / addtocart / transaction), 상품]"""
    return [
        [round((t - start) / 1000, 1), str(e), int(i)]
        for t, e, i in frame[["timestamp", "event", "itemid"]].itertuples(index=False)
    ]


def main():
    events, _ = load_events()
    users = pd.read_parquet(output_dir / "users.parquet")
    test_users = set(users.loc[users["split"] == "test", "visitorid"])
    start = int(pd.Timestamp(DATE, tz="UTC").value // 1_000_000) + START_HOUR * 3_600_000
    end = start + WINDOW_MINUTES * 60_000

    by_type = {kind: [] for kind in TYPES}
    for uid, kind, visit, history in window_visits(events, test_users, start, end):
        by_type[kind].append((visit, history))

    rng = np.random.default_rng(SEED)
    customers = []
    for kind, label in TYPES.items():
        pool = by_type[kind]
        print(f"{label}: 후보 {len(pool)}명")
        for index in sorted(rng.choice(len(pool), size=min(PER_TYPE, len(pool)), replace=False)):
            visit, history = pool[index]
            customers.append({"type": kind, "label": label, "visit": visit, "history": history})
    # 탭 번호는 들어온 순서대로 매긴다.
    customers.sort(key=lambda c: c["visit"]["timestamp"].iloc[0])

    result = []
    for number, c in enumerate(customers, start=1):
        result.append({
            "id": number,
            "type": c["type"],
            "label": c["label"],
            "history": as_rows(c["history"], start),
            "events": as_rows(c["visit"], start),
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "source": "RetailRocket test 기간 고객의 실제 기록. 고객 번호는 새로 매김",
                "window": {
                    "date": DATE,
                    "start": pd.Timestamp(start, unit="ms", tz="UTC").isoformat(),
                    "start_minute": START_HOUR * 60,
                    "minutes": WINDOW_MINUTES,
                },
                "customers": result,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    for c in result:
        first, last = c["events"][0][0], c["events"][-1][0]
        print(
            f"  {c['id']}. {c['label']}: {first / 60:.0f}분에 들어와 {last / 60:.0f}분까지, "
            f"행동 {len(c['events'])}개, 이전 기록 {len(c['history'])}개"
        )
    print(f"저장: {OUTPUT}")


if __name__ == "__main__":
    main()
