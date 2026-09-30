"""조회 시점별·후보 상품별 학습 데이터를 만든다.

샘플링하지 않고 전체 사용자의 모든 조회 시점을 사용한다.
split_users.py로 만든 사용자 분리에 따라 train/valid/test Parquet 파일로 저장한다.
"""
import json
from collections import defaultdict
from time import perf_counter

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from events import first_purchase_times, load_events, output_dir, sorted_views
from features import FEATURES, UserViewState


NO_PURCHASE = np.iinfo(np.int64).max
FLUSH_ROWS = 2_000_000
COLUMNS = ["visitorid", "cutoff_timestamp", "itemid", "heavy_user", *FEATURES, "label"]


class SplitWriter:
    """구간별로 행을 모아 Parquet 파일에 나눠 쓴다."""

    def __init__(self, path):
        self.path = path
        self.writer = None
        self.buffer = defaultdict(list)
        self.buffered = 0
        self.rows = 0
        self.positives = 0

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
        table = pa.table(
            {name: np.concatenate(self.buffer[name]) for name in COLUMNS}
        )
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
    started = perf_counter()
    print("이벤트를 읽습니다.", flush=True)
    events, duplicate_counts = load_events()
    views = sorted_views(events)

    users = pd.read_parquet(output_dir / "users.parquet").set_index("visitorid")
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
    del events

    visitor = views["visitorid"].to_numpy()
    timestamp = views["timestamp"].to_numpy()
    item = views["itemid"].to_numpy()
    del views

    # 사용자가 바뀌거나 시각이 바뀌는 위치가 예측 시점의 시작이다.
    point_start = np.flatnonzero(
        np.r_[True, (visitor[1:] != visitor[:-1]) | (timestamp[1:] != timestamp[:-1])]
    )
    point_end = np.r_[point_start[1:], len(visitor)]
    user_first_point = np.flatnonzero(
        np.r_[True, visitor[point_start[1:]] != visitor[point_start[:-1]]]
    )
    user_last_point = np.r_[user_first_point[1:], len(point_start)]

    target_dir = output_dir / "training_rows"
    target_dir.mkdir(parents=True, exist_ok=True)
    writers = {
        name: SplitWriter(target_dir / f"{name}.parquet")
        for name in ("train", "valid", "test")
    }
    excluded_points = 0
    excluded_rows = 0
    user_rows = {}
    user_positives = {}

    for first, last in tqdm(
        zip(user_first_point, user_last_point),
        total=len(user_first_point),
        desc="사용자",
        mininterval=5,
    ):
        uid = int(visitor[point_start[first]])
        writer = writers[split_of[uid]]
        heavy = heavy_of[uid]
        buys = first_buy.get(uid, {})
        pending_buys = sorted((t, i) for i, t in buys.items())
        buy_index = 0
        buy_times = purchase_times.get(uid, set())
        state = UserViewState()
        buy_of_position = []
        rows = positives = 0

        for p in range(first, last):
            start, end = point_start[p], point_end[p]
            now = int(timestamp[start])

            while buy_index < len(pending_buys) and pending_buys[buy_index][0] <= now:
                state.mark_purchased(pending_buys[buy_index][1])
                buy_index += 1

            size_before = state.size
            state.add_views(now, item[start:end].tolist())
            for pos in range(size_before, state.size):
                buy_of_position.append(buys.get(int(state.items[pos]), NO_PURCHASE))

            positions = state.candidates()
            if now in buy_times:
                # 조회와 구매의 선후를 알 수 없으므로 이 예측 시점은 제외한다.
                excluded_points += 1
                excluded_rows += len(positions)
                continue
            if len(positions) == 0:
                continue

            label = (np.asarray(buy_of_position)[positions] != NO_PURCHASE).astype(
                np.int8
            )
            count = len(positions)
            columns = {
                "visitorid": np.full(count, uid, dtype=np.int32),
                "cutoff_timestamp": np.full(count, now, dtype=np.int64),
                "itemid": state.items[positions].astype(np.int32),
                "heavy_user": np.full(count, heavy, dtype=np.int8),
                **state.features(now, positions),
                "label": label,
            }
            writer.add(columns)
            rows += count
            positives += int(label.sum())

        user_rows[uid] = rows
        user_positives[uid] = positives

    for writer in writers.values():
        writer.close()

    users["n_rows"] = pd.Series(user_rows)
    users["n_positive_rows"] = pd.Series(user_positives)
    users = users.fillna({"n_rows": 0, "n_positive_rows": 0})
    users = users.astype({"n_rows": "int64", "n_positive_rows": "int64"})
    users.reset_index().to_parquet(output_dir / "users.parquet", index=False)

    report = {
        "duplicate_rows_removed": duplicate_counts,
        "excluded_same_time_points": excluded_points,
        "excluded_same_time_rows": excluded_rows,
        "splits": {},
        "elapsed_seconds": round(perf_counter() - started, 1),
    }
    for name, writer in writers.items():
        in_split = users["split"] == name
        heavy = in_split & (users["heavy_user"] == 1)
        report["splits"][name] = {
            "rows": writer.rows,
            "positive_rows": writer.positives,
            "positive_rate": writer.positives / writer.rows if writer.rows else 0.0,
            "heavy_user_rows": int(users.loc[heavy, "n_rows"].sum()),
            "heavy_user_positive_rows": int(users.loc[heavy, "n_positive_rows"].sum()),
            "max_user_row_share": float(
                users.loc[in_split, "n_rows"].max() / writer.rows
            )
            if writer.rows
            else 0.0,
        }
    (output_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"제거한 중복 행: {duplicate_counts}")
    print(f"같은 시각 조회·구매로 제외한 예측 시점: {excluded_points:,}개")
    for name, values in report["splits"].items():
        print(
            f"{name}: 행 {values['rows']:,}개 / 정답 1 {values['positive_rows']:,}개 "
            f"({values['positive_rate']:.3%}) / "
            f"과다 조회 사용자 행 {values['heavy_user_rows'] / max(values['rows'], 1):.1%} / "
            f"최대 1인 행 비중 {values['max_user_row_share']:.1%}"
        )
    print(f"소요 시간: {report['elapsed_seconds']:,}초")


if __name__ == "__main__":
    main()
