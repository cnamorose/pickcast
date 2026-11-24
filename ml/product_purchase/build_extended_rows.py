"""조회·장바구니 시점별, 후보 상품별 확장 피처 학습 데이터를 만든다 (판매자용 모델 실험).

build_training_rows.py와 같은 방식이고 다음이 다르다.
- 장바구니 담기도 예측 시점이다. 조회하지 않고 담은 상품도 후보에 넣는다.
- 피처는 features_extended.py의 모든 묶음을 한 번에 만든다. 실험마다 필요한 열만 골라 쓴다.
- touched_now: 그 시각에 조회했거나 담은 상품인지 (피처가 아니라 평가용)

정답은 같다: 예측 시점 이후 그 상품을 구매했는가. split_by_time.py의 분할을 쓴다.

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/build_extended_rows.py
"""
import json
from collections import defaultdict
from time import perf_counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

import item_stats
from events import DEFAULT_OUTPUT_NAME, first_purchase_times, load_events, output_dir
from features_extended import ALL_FEATURES, UserEventState
from modeling import extended_rows_dir as rows_dir


NO_PURCHASE = np.iinfo(np.int64).max
FLUSH_ROWS = 2_000_000
COLUMNS = [
    "visitorid", "cutoff_timestamp", "itemid", "heavy_user", "touched_now",
    *ALL_FEATURES, "label",
]


class SplitWriter:
    """구간별로 행을 모아 상품 통계를 붙인 뒤 Parquet 파일에 나눠 쓴다."""

    def __init__(self, name, stats):
        self.name = name
        self.stats = stats
        self.path = rows_dir / f"{name}.parquet"
        self.writer = None
        self.buffer = defaultdict(list)
        self.buffered = 0
        self.rows = 0
        self.positives = 0
        self.cart_points = 0

    def add(self, columns):
        for name, values in columns.items():
            self.buffer[name].append(values)
        count = len(columns["label"])
        self.buffered += count
        self.rows += count
        self.positives += int(columns["label"].sum())
        if self.buffered >= FLUSH_ROWS:
            self.flush()

    def flush(self):
        if not self.buffered:
            return
        frame = pd.DataFrame({name: np.concatenate(values) for name, values in self.buffer.items()})
        frame = item_stats.attach(frame, self.name, *self.stats)
        table = pa.Table.from_pandas(frame[COLUMNS], preserve_index=False)
        if self.writer is None:
            self.writer = pq.ParquetWriter(self.path, table.schema, compression="zstd")
        self.writer.write_table(table)
        self.buffer.clear()
        self.buffered = 0

    def close(self):
        self.flush()
        if self.writer is not None:
            self.writer.close()


def main():
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit("시간 분할 실험 폴더에서 실행하세요 (PRODUCT_PURCHASE_DIR).")
    started = perf_counter()
    print("이벤트를 읽습니다.", flush=True)
    events, _ = load_events()
    users = pd.read_parquet(output_dir / "users.parquet")
    print("train 기간 상품 통계를 계산합니다.", flush=True)
    stats = item_stats.compute(events, users)

    users = users.set_index("visitorid")
    split_of = users["split"].astype(str).to_dict()
    heavy_of = users["heavy_user"].to_dict()

    first_buy = defaultdict(dict)
    for (visitor, item), timestamp in first_purchase_times(events).items():
        first_buy[visitor][item] = timestamp
    purchase_times = (
        events.loc[events["event"] == "transaction"]
        .groupby("visitorid")["timestamp"]
        .agg(set)
        .to_dict()
    )

    touches = events.loc[
        events["event"].isin(["view", "addtocart"]), ["visitorid", "timestamp", "itemid", "event"]
    ]
    touches = touches.sort_values(["visitorid", "timestamp"], kind="stable").reset_index(drop=True)
    del events
    visitor = touches["visitorid"].to_numpy()
    timestamp = touches["timestamp"].to_numpy()
    item = touches["itemid"].to_numpy()
    is_cart = (touches["event"] == "addtocart").to_numpy()
    del touches

    point_start = np.flatnonzero(
        np.r_[True, (visitor[1:] != visitor[:-1]) | (timestamp[1:] != timestamp[:-1])]
    )
    point_end = np.r_[point_start[1:], len(visitor)]
    user_first_point = np.flatnonzero(
        np.r_[True, visitor[point_start[1:]] != visitor[point_start[:-1]]]
    )
    user_last_point = np.r_[user_first_point[1:], len(point_start)]

    rows_dir.mkdir(parents=True, exist_ok=True)
    writers = {name: SplitWriter(name, stats) for name in ("train", "valid", "test")}
    excluded_points = 0

    for first, last in tqdm(
        zip(user_first_point, user_last_point),
        total=len(user_first_point),
        desc="사용자",
        mininterval=5,
    ):
        uid = int(visitor[point_start[first]])
        # 조회 없이 담기만 한 사용자는 users.parquet에 없다. 학습에 쓰지 않는다.
        writer = writers.get(split_of.get(uid))
        if writer is None:
            continue
        heavy = heavy_of[uid]
        buys = first_buy.get(uid, {})
        pending_buys = sorted((t, i) for i, t in buys.items())
        buy_index = 0
        buy_times = purchase_times.get(uid, set())
        state = UserEventState()
        buy_of_position = []

        for p in range(first, last):
            start, end = point_start[p], point_end[p]
            now = int(timestamp[start])

            while buy_index < len(pending_buys) and pending_buys[buy_index][0] <= now:
                state.mark_purchased(pending_buys[buy_index][1])
                buy_index += 1

            size_before = state.size
            carts = is_cart[start:end]
            state.add_events(now, item[start:end][~carts].tolist(), item[start:end][carts].tolist())
            for pos in range(size_before, state.size):
                buy_of_position.append(buys.get(int(state.items[pos]), NO_PURCHASE))

            positions = state.candidates()
            if now in buy_times:
                # 조회·담기와 구매의 선후를 알 수 없으므로 이 예측 시점은 제외한다.
                excluded_points += 1
                continue
            if len(positions) == 0:
                continue

            label = (np.asarray(buy_of_position)[positions] != NO_PURCHASE).astype(np.int8)
            count = len(positions)
            writer.add(
                {
                    "visitorid": np.full(count, uid, dtype=np.int32),
                    "cutoff_timestamp": np.full(count, now, dtype=np.int64),
                    "itemid": state.items[positions].astype(np.int32),
                    "heavy_user": np.full(count, heavy, dtype=np.int8),
                    "touched_now": state.touched_now(now, positions),
                    **state.features(now, positions),
                    "label": label,
                }
            )
            writer.cart_points += int(carts.any())

    for writer in writers.values():
        writer.close()

    report = {
        "excluded_same_time_points": excluded_points,
        "item_stats_defaults": {k: float(v) for k, v in stats[1].items()},
        "splits": {
            name: {
                "rows": w.rows,
                "positive_rows": w.positives,
                "positive_rate": w.positives / w.rows if w.rows else 0.0,
                "points_with_cart": w.cart_points,
            }
            for name, w in writers.items()
        },
        "elapsed_seconds": round(perf_counter() - started, 1),
    }
    (rows_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"같은 시각 구매로 제외한 예측 시점: {excluded_points:,}개")
    for name, values in report["splits"].items():
        print(
            f"{name}: 행 {values['rows']:,}개 / 정답 1 {values['positive_rows']:,}개 "
            f"({values['positive_rate']:.3%}) / 담기가 있는 예측 시점 {values['points_with_cart']:,}개"
        )
    print(f"소요 시간: {report['elapsed_seconds']:,}초")


if __name__ == "__main__":
    main()
