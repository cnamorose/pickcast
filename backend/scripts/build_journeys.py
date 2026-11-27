"""시뮬레이션 화면(손님 한 명 따라가기)에 쓸 손님 기록을 원본에서 골라 작은 파일로 저장한다.

모델(v3)이 학습·보정에 쓰지 않은 test 기간(2015-08-01 ~ 09-18) 고객 중, 기록 전체가 한 번의
방문(행동 사이 30분 이내)인 고객만 고른다. 그래야 화면에 보이는 기록이 모델이 보는 기록 전부다.
유형별로 고정 시드로 무작위 3명씩 고르고, AI가 맞혔는지는 고른 뒤에 API가 계산한다
(잘 맞힌 손님만 고르지 않는다).

- compare_buy: 여러 상품(3개 이상)을 보고 담은 뒤 산 손님
- cart_leave: 담았지만 사지 않고 떠난 손님 (이후에도 사지 않음)
- quick_buy: 몇 개(3개 이하)만 보고 15분 안에 산 손님

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
VISIT_GAP_MS = 30 * 60_000
MIN_EVENTS, MAX_EVENTS = 5, 25
MAX_MINUTES = 90
PER_TYPE = 3
SEED = 7
TYPES = {
    "compare_buy": "여러 상품을 비교하다 담고 산 손님",
    "cart_leave": "담았지만 사지 않고 떠난 손님",
    "quick_buy": "몇 개만 보고 바로 산 손님",
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


def candidate_visits(events, users):
    """기록 전체가 한 번의 방문이고 길이가 적당한 test 고객의 기록."""
    mine = events[events["visitorid"].isin(users)].sort_values(["visitorid", "timestamp"], kind="stable")
    for uid, visit in mine.groupby("visitorid", sort=True):
        times = visit["timestamp"].to_numpy()
        if not MIN_EVENTS <= len(visit) <= MAX_EVENTS:
            continue
        if (np.diff(times) > VISIT_GAP_MS).any() or (times[-1] - times[0]) > MAX_MINUTES * 60_000:
            continue
        kind = visit_type(visit)
        if kind:
            yield uid, kind, visit


def main():
    events, _ = load_events()
    users = pd.read_parquet(output_dir / "users.parquet")
    test_users = set(users.loc[users["split"] == "test", "visitorid"])

    by_type = {kind: [] for kind in TYPES}
    for uid, kind, visit in candidate_visits(events, test_users):
        by_type[kind].append((uid, visit))

    rng = np.random.default_rng(SEED)
    customers = []
    for kind, label in TYPES.items():
        pool = by_type[kind]
        print(f"{label}: 후보 {len(pool):,}명")
        for index in sorted(rng.choice(len(pool), size=min(PER_TYPE, len(pool)), replace=False)):
            _, visit = pool[index]
            start = int(visit["timestamp"].iloc[0])
            customers.append({
                "id": len(customers) + 1,
                "type": kind,
                "label": label,
                "started_at": pd.Timestamp(start, unit="ms", tz="UTC").isoformat(),
                # [첫 기록부터 초, 종류(view / addtocart / transaction), 상품]
                "events": [
                    [round((t - start) / 1000, 1), str(e), int(i)]
                    for t, e, i in visit[["timestamp", "event", "itemid"]].itertuples(index=False)
                ],
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "source": "RetailRocket test 기간(2015-08-01 ~ 09-18) 고객의 실제 기록. 고객 번호는 새로 매김",
                "customers": customers,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    for c in customers:
        print(f"  {c['id']}. {c['label']}: 기록 {len(c['events'])}개, {c['events'][-1][0] / 60:.1f}분")
    print(f"저장: {OUTPUT}")


if __name__ == "__main__":
    main()
