"""시뮬레이션 화면(판매자 대시보드 재생)이 쓸 하루치 재생 파일을 만든다.

test 기간(8~9월) 하루를 골라, 1분마다 그때 쇼핑 중인 고객의 v3 예측으로 대시보드 상태를 미리
계산한다. 모델은 이 기간을 학습·보정에 쓰지 않았고, 10분 예상 판매는 evaluate_horizon.py로
같은 test 고객에서 확인했다. 여러 기간에 걸친 고객(제외 사용자)은 넣지 않는다.

파일 내용 (ml/results/replay/날짜.json)
- snapshots: 1분마다
  - shoppers: 최근 30분 안에 보거나 담은 고객 수 / carting: 최근 30분 안에 담은 고객 수
  - expected_next_10m: 다음 10분 예상 판매 합 (최근 24시간 안에 행동한 고객의 후보 상품)
  - top_items: 예상 판매 상위 상품 [상품, 예상 판매, 1개 이상 팔릴 확률, 후보로 둔 고객 수]
- events: 그날의 조회(v)·담기(c)·구매(b) [시작부터 초, 고객 번호, 종류, 상품]
- purchases: 구매마다 모델이 미리 알았는지 [초, 고객, 상품, 확률, 순위, 후보 수, 예측 시점부터 분]
  산 상품을 방금 보거나 담은 시점(결제하러 들어간 조회)이면 한 시점 앞의 예측을 쓴다.
  보거나 담지 않고 산 구매는 확률·순위가 없다(null).

고객 번호는 그날 처음 나온 순서로 1부터 다시 매긴다. 시각은 UTC다.

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/build_replay.py --version v3 --date 2015-08-17
"""
import argparse
import json
import math

import numpy as np
import pandas as pd

from events import DEFAULT_OUTPUT_NAME, load_events, ml_dir, output_dir
from horizon import ACTIVE_MINUTES, HORIZON_MINUTES, load_rates, within_horizon
from horizon_rows import MINUTE, predict_split, purchase_times, window_pairs
from release import release_dir
from split_by_time import TEST_START

DAY_MINUTES = 24 * 60
SHOPPING_MINUTES = 30
TOP_ITEMS = 10
REPLAY_DIR = ml_dir / "results" / "replay"
EVENT_CODES = {"view": "v", "addtocart": "c", "transaction": "b"}
# 한 번에 펼치는 행 수. 행 하나가 최대 1,440분이라 작게 둔다.
CHUNK_ROWS = 5_000


def active_counts(users, times, start, minutes, window_minutes=SHOPPING_MINUTES):
    """1분마다(시각 start + k분) 최근 window_minutes 안에 행동한 서로 다른 고객 수.

    시각 t에는 t − window < 행동 시각 <= t 인 고객을 센다.
    """
    times = np.asarray(times, dtype=np.int64)
    first = -((start - times) // MINUTE)                               # k >= 행동 시각 (올림)
    end = -((start - times - window_minutes * MINUTE) // MINUTE)      # k < 행동 시각 + window
    frame = pd.DataFrame({"user": np.asarray(users), "a": first, "b": end}).sort_values(["user", "a"])
    # 같은 고객의 겹치는 구간은 한 번만 센다: 앞선 구간들의 끝 중 최댓값 뒤부터만 더한다.
    previous_end = frame.groupby("user")["b"].cummax().groupby(frame["user"]).shift().fillna(-np.inf)
    a = np.maximum(frame["a"].to_numpy(), previous_end.to_numpy())
    b = frame["b"].to_numpy()
    keep = a < b
    a = np.clip(a[keep], 0, minutes).astype(np.int64)
    b = np.clip(b[keep], 0, minutes).astype(np.int64)
    diff = np.zeros(minutes + 1)
    np.add.at(diff, a, 1)
    np.add.at(diff, b, -1)
    return np.cumsum(diff)[:minutes].astype(int)


def minute_forecasts(frame, p, bought, rates, start, minutes, top=TOP_ITEMS):
    """1분마다 다음 10분 예상 판매 합과 예상 판매 상위 상품."""
    carted = frame["cart_count"].to_numpy() > 0
    items = frame["itemid"].to_numpy()
    totals = np.zeros(minutes)
    parts = []
    for row, k, elapsed, _ in window_pairs(
        frame, bought, start, minutes, MINUTE, ACTIVE_MINUTES, chunk_rows=CHUNK_ROWS
    ):
        q = within_horizon(p[row], elapsed, carted[row], rates)
        totals += np.bincount(k, weights=q, minlength=minutes)
        keep = q > 0
        part = pd.DataFrame({
            "k": k[keep],
            "item": items[row][keep],
            "q": q[keep],
            "log_miss": np.log1p(-np.minimum(q[keep], 1 - 1e-12)),
        })
        parts.append(
            part.groupby(["k", "item"], sort=False).agg(
                expected=("q", "sum"), log_miss=("log_miss", "sum"), customers=("q", "size")
            )
        )
    top_items = [[] for _ in range(minutes)]
    if parts:
        agg = pd.concat(parts).groupby(level=[0, 1]).sum().reset_index()
        agg = agg.sort_values(["k", "expected", "item"], ascending=[True, False, True])
        for k, item, expected, log_miss, customers in agg.groupby("k").head(top).itertuples(index=False):
            top_items[int(k)].append(
                [int(item), round(float(expected), 4), round(1 - math.exp(log_miss), 4), int(customers)]
            )
    return totals, top_items


def purchase_checks(frame, p, purchases):
    """구매마다 산 직전 예측 시점에서 그 상품의 확률·순위·후보 수·예측 시점부터 걸린 분.

    purchases: (visitorid, itemid, 구매 시각) 목록. 산 상품을 그 시점에 방금 보거나 담았다면
    한 시점 앞을 본다. 볼 시점이 없거나 그 시점의 후보가 아니면 None을 돌려준다.
    """
    visitor = frame["visitorid"].to_numpy()
    cutoff = frame["cutoff_timestamp"].to_numpy()
    items = frame["itemid"].to_numpy()
    touched = frame["touched_now"].to_numpy()
    rows_of = pd.Series(np.arange(len(frame))).groupby(visitor).apply(np.asarray).to_dict()

    results = []
    for user, item, bought_at in purchases:
        rows = rows_of.get(user)
        if rows is None:
            results.append(None)
            continue
        times = np.unique(cutoff[rows][cutoff[rows] < bought_at])
        if len(times) == 0:
            results.append(None)
            continue
        point = times[-1]
        here = rows[(cutoff[rows] == point) & (items[rows] == item)]
        if len(here) and touched[here[0]]:
            if len(times) < 2:
                results.append(None)
                continue
            point = times[-2]
        candidates = rows[cutoff[rows] == point]
        match = candidates[items[candidates] == item]
        if len(match) == 0:
            results.append(None)
            continue
        probability = p[match[0]]
        rank = int((p[candidates] > probability).sum()) + 1
        results.append(
            (float(probability), rank, int(len(candidates)), float((bought_at - point) / MINUTE))
        )
    return results


def build_day(directory, date, frame, p, bought, events, rates):
    start = int(pd.Timestamp(date, tz="UTC").value // 1_000_000)
    end = start + DAY_MINUTES * MINUTE
    users = pd.unique(frame["visitorid"])

    window = (frame["cutoff_timestamp"] >= start - ACTIVE_MINUTES * MINUTE) & (frame["cutoff_timestamp"] < end)
    day_rows = frame.index[window.to_numpy()]
    day_frame = frame.loc[day_rows].reset_index(drop=True)
    day_p, day_bought = p[day_rows], bought[day_rows]
    expected, top_items = minute_forecasts(day_frame, day_p, day_bought, rates, start, DAY_MINUTES)

    mine = events[events["visitorid"].isin(users)]
    recent = mine[(mine["timestamp"] > start - SHOPPING_MINUTES * MINUTE) & (mine["timestamp"] < end)]
    touches = recent[recent["event"].isin(["view", "addtocart"])]
    carts = recent[recent["event"] == "addtocart"]
    shoppers = active_counts(touches["visitorid"], touches["timestamp"], start, DAY_MINUTES)
    carting = active_counts(carts["visitorid"], carts["timestamp"], start, DAY_MINUTES)

    day = mine[(mine["timestamp"] >= start) & (mine["timestamp"] < end)].sort_values("timestamp", kind="stable")
    code = {user: i + 1 for i, user in enumerate(pd.unique(day["visitorid"]))}
    event_rows = [
        [round((t - start) / 1000, 1), code[u], EVENT_CODES[str(e)], int(i)]
        for t, u, e, i in day[["timestamp", "visitorid", "event", "itemid"]].itertuples(index=False)
    ]

    sales = day[day["event"] == "transaction"].groupby(["visitorid", "itemid"])["timestamp"].min()
    first_sales = sales[sales.to_numpy() == bought_first(events, sales.index)]
    first_sales = first_sales.sort_values()
    checks = purchase_checks(
        day_frame, day_p, [(u, i, t) for (u, i), t in first_sales.items()]
    )
    purchase_rows = []
    for ((u, i), t), check in zip(first_sales.items(), checks):
        probability, rank, candidates, before = check if check else (None, None, None, None)
        purchase_rows.append([
            round((t - start) / 1000, 1), code[u], int(i),
            None if probability is None else round(probability, 4), rank, candidates,
            None if before is None else round(before, 1),
        ])

    window_sum = float(expected[::HORIZON_MINUTES].sum())
    return {
        "date": date,
        "version": directory.name,
        "timezone": "UTC",
        "minutes": DAY_MINUTES,
        "horizon_minutes": HORIZON_MINUTES,
        "shopping_minutes": SHOPPING_MINUTES,
        "customers": "test 기간(8~9월) 사용자만. 여러 기간에 걸친 고객은 넣지 않았다.",
        "summary": {
            "customers": len(code),
            "events": len(event_rows),
            "purchases": len(purchase_rows),
            "expected_sales_10m_windows": round(window_sum, 2),
            "known_before_purchase": sum(1 for c in checks if c is not None),
            "top1_hits": sum(1 for c in checks if c is not None and c[1] == 1),
        },
        "snapshots": {
            "shoppers": shoppers.tolist(),
            "carting": carting.tolist(),
            "expected_next_10m": [round(float(x), 4) for x in expected],
            "top_items": top_items,
            "top_item_columns": ["item", "expected", "at_least_one", "customers"],
        },
        "events": {"columns": ["second", "customer", "type", "item"], "rows": event_rows},
        "purchases": {
            "columns": ["second", "customer", "item", "probability", "rank", "candidates", "minutes_before"],
            "rows": purchase_rows,
        },
    }


def bought_first(events, index):
    """(visitorid, itemid)별 전체 기간 첫 구매 시각. 그날 산 것이 첫 구매인지 확인하는 데 쓴다."""
    purchases = events[events["event"] == "transaction"]
    first = purchases.groupby(["visitorid", "itemid"])["timestamp"].min()
    return first.reindex(index).to_numpy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", action="append", required=True, help="YYYY-MM-DD (여러 번 쓸 수 있음)")
    args = parser.parse_args()
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit("시간 분할 실험 폴더에서 실행하세요 (PRODUCT_PURCHASE_DIR).")
    for date in args.date:
        start = pd.Timestamp(date, tz="UTC").value // 1_000_000
        if start < TEST_START:
            raise SystemExit(f"test 기간(2015-08-01부터)의 날짜만 재생합니다: {date}")

    directory = release_dir(args.version)
    rates = load_rates(directory)
    print("test 행의 확률을 계산합니다.", flush=True)
    frame, p = predict_split(directory, "test", extra_columns=["touched_now"])
    events, _ = load_events()
    bought = purchase_times(frame, events)

    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    for date in args.date:
        print(f"{date}를 계산합니다.", flush=True)
        replay = build_day(directory, date, frame, p, bought, events, rates)
        path = REPLAY_DIR / f"{date}.json"
        path.write_text(json.dumps(replay, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        s = replay["summary"]
        print(
            f"  고객 {s['customers']:,}, 기록 {s['events']:,}, 구매 {s['purchases']}, "
            f"10분 예상 합 {s['expected_sales_10m_windows']:.1f}, "
            f"미리 본 구매 {s['known_before_purchase']} 중 1순위 {s['top1_hits']}, "
            f"{path.stat().st_size / 1e6:.2f}MB → {path}"
        )


if __name__ == "__main__":
    main()
