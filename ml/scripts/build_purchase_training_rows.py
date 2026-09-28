import csv
import random
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from tqdm import tqdm

HOUR_MS = 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
SNAPSHOT_SAMPLE_RATE = 0.10
RANDOM_SEED = 42


def main():
    ml_dir = Path(__file__).resolve().parents[1]
    events = pd.read_csv(
        ml_dir / "data" / "raw" / "events.csv",
        usecols=["timestamp", "visitorid", "event", "itemid"],
    )
    data_end = int(events["timestamp"].max())

    purchase_times = defaultdict(list)
    purchase_at = defaultdict(set)

    purchases = events.loc[
        events["event"].eq("transaction"),
        ["visitorid", "itemid", "timestamp"],
    ]
    for visitor, item, timestamp in purchases.itertuples(index=False, name=None):
        visitor, item, timestamp = int(visitor), int(item), int(timestamp)
        purchase_times[(visitor, item)].append(timestamp)
        purchase_at[visitor].add(timestamp)

    for times in purchase_times.values():
        times.sort()

    views = (
        events.loc[
            events["event"].eq("view"),
            ["visitorid", "timestamp", "itemid"],
        ]
        .sort_values(["visitorid", "timestamp"], kind="stable")
    )
    del events, purchases

    output_dir = ml_dir / "data" / "processed" / "product_purchase_v2"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "training_rows.csv"
    temp_path = output_dir / "training_rows.csv.tmp"

    columns = [
        "visitorid",
        "cutoff_timestamp",
        "label_end_timestamp",
        "itemid",
        "view_count",
        "view_share",
        "seconds_since_first_view",
        "seconds_since_last_view",
        "views_last_hour",
        "views_last_day",
        "user_total_views",
        "candidate_count",
        "label",
    ]

    rng = random.Random(RANDOM_SEED)
    stats = Counter()
    counts = Counter()
    first_view = {}
    last_view = {}
    view_times = defaultdict(list)
    total_views = 0
    current_visitor = None
    current_cutoff = None

    with temp_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(columns)

        def write_snapshot(visitor, cutoff):
            stats["all_snapshots"] += 1

            # 이후 24시간의 구매 기록을 온전히 확인할 수 있어야 합니다.
            if cutoff + DAY_MS > data_end:
                stats["incomplete_window"] += 1
                return

            # 조회와 구매가 같은 시각이면 순서를 알 수 없어 제외합니다.
            if cutoff in purchase_at.get(visitor, ()):
                stats["same_time_purchase"] += 1
                return

            # 상품이 아니라 예측 시점을 무작위로 선택합니다.
            if rng.random() >= SNAPSHOT_SAMPLE_RATE:
                return

            stats["selected_snapshots"] += 1

            for item, count in counts.items():
                times = purchase_times.get((visitor, item), ())
                next_index = bisect_right(times, cutoff)
                label = int(
                    next_index < len(times)
                    and times[next_index] <= cutoff + DAY_MS
                )

                writer.writerow([
                    visitor,
                    cutoff,
                    cutoff + DAY_MS,
                    item,
                    count,
                    count / total_views,
                    (cutoff - first_view[item]) / 1000,
                    (cutoff - last_view[item]) / 1000,
                    count - bisect_left(view_times[item], cutoff - HOUR_MS),
                    count - bisect_left(view_times[item], cutoff - DAY_MS),
                    total_views,
                    len(counts),
                    label,
                ])
                stats["rows"] += 1
                stats["positive_rows"] += label

        for visitor, timestamp, item in tqdm(
            views.itertuples(index=False, name=None),
            total=len(views),
            desc="상품별 학습 데이터 생성",
            unit="view",
        ):
            visitor = int(visitor)
            timestamp = int(timestamp)
            item = int(item)

            if (visitor, timestamp) != (current_visitor, current_cutoff):
                if current_cutoff is not None:
                    write_snapshot(current_visitor, current_cutoff)

                if visitor != current_visitor:
                    counts.clear()
                    first_view.clear()
                    last_view.clear()
                    view_times.clear()
                    total_views = 0

                current_visitor = visitor
                current_cutoff = timestamp

            counts[item] += 1
            first_view.setdefault(item, timestamp)
            last_view[item] = timestamp
            view_times[item].append(timestamp)
            total_views += 1

        if current_cutoff is not None:
            write_snapshot(current_visitor, current_cutoff)

    # 끝까지 생성된 파일만 최종 이름으로 저장합니다.
    temp_path.replace(output_path)

    print(f"전체 예측 시점: {stats['all_snapshots']:,}")
    print(f"선택한 예측 시점: {stats['selected_snapshots']:,}")
    print(f"관찰 기간 부족으로 제외: {stats['incomplete_window']:,}")
    print(f"동일 시각 구매로 제외: {stats['same_time_purchase']:,}")
    print(f"학습용 상품 행: {stats['rows']:,}")
    print(f"label=1: {stats['positive_rows']:,}")
    print(f"label=0: {stats['rows'] - stats['positive_rows']:,}")
    print(f"저장 위치: {output_path}")


if __name__ == "__main__":
    main()
