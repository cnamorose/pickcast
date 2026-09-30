import csv
import math
import random
from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path

import pandas as pd


HOUR_MS = 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
SAMPLE_SIZE = 100
rng = random.Random(123)

ml_dir = Path(__file__).resolve().parents[2]
rows_path = ml_dir / "data" / "experiments" / "within_24h" / "processed" / "training_rows.csv"

random_rows = []
positive_rows = []
row_count = 0
positive_count = 0

# 큰 CSV를 전부 메모리에 올리지 않고 행을 골고루 추출합니다.
with rows_path.open(newline="", encoding="utf-8") as file:
    for row in csv.DictReader(file):
        row_count += 1
        if len(random_rows) < SAMPLE_SIZE:
            random_rows.append(row)
        else:
            index = rng.randrange(row_count)
            if index < SAMPLE_SIZE:
                random_rows[index] = row

        if row["label"] == "1":
            positive_count += 1
            if len(positive_rows) < SAMPLE_SIZE:
                positive_rows.append(row)
            else:
                index = rng.randrange(positive_count)
                if index < SAMPLE_SIZE:
                    positive_rows[index] = row

selected_rows = random_rows + positive_rows
selected_users = {int(row["visitorid"]) for row in selected_rows}

events = pd.read_csv(
    ml_dir / "data" / "raw" / "events.csv",
    usecols=["timestamp", "visitorid", "event", "itemid"],
)
events = events.loc[events["visitorid"].isin(selected_users)]

user_views = defaultdict(list)
item_views = defaultdict(list)
purchases = defaultdict(list)

for timestamp, visitor, event, item in events[
    ["timestamp", "visitorid", "event", "itemid"]
].itertuples(index=False, name=None):
    timestamp, visitor, item = int(timestamp), int(visitor), int(item)
    if event == "view":
        user_views[visitor].append(timestamp)
        item_views[(visitor, item)].append(timestamp)
    elif event == "transaction":
        purchases[(visitor, item)].append(timestamp)

for times in list(user_views.values()) + list(item_views.values()) + list(purchases.values()):
    times.sort()

first_view_times = defaultdict(list)
for (visitor, _item), times in item_views.items():
    first_view_times[visitor].append(times[0])
for times in first_view_times.values():
    times.sort()

for row in selected_rows:
    visitor = int(row["visitorid"])
    item = int(row["itemid"])
    cutoff = int(row["cutoff_timestamp"])
    label_end = int(row["label_end_timestamp"])

    assert label_end == cutoff + DAY_MS

    views_for_item = item_views[(visitor, item)]
    view_count = bisect_right(views_for_item, cutoff)
    total_views = bisect_right(user_views[visitor], cutoff)
    assert view_count > 0
    assert int(row["view_count"]) == view_count

    expected_share = view_count / total_views
    expected_first = (cutoff - views_for_item[0]) / 1000
    expected_last = (cutoff - views_for_item[view_count - 1]) / 1000

    for column, expected in [
        ("view_share", expected_share),
        ("seconds_since_first_view", expected_first),
        ("seconds_since_last_view", expected_last),
    ]:
        assert math.isclose(float(row[column]), expected, abs_tol=1e-6), (
            visitor, item, cutoff, column
        )

    expected_counts = {
        "views_last_hour": view_count - bisect_left(
            views_for_item, cutoff - HOUR_MS
        ),
        "views_last_day": view_count - bisect_left(
            views_for_item, cutoff - DAY_MS
        ),
        "user_total_views": total_views,
        "candidate_count": bisect_right(first_view_times[visitor], cutoff),
    }
    for column, expected in expected_counts.items():
        assert int(row[column]) == expected, (visitor, item, cutoff, column)

    purchase_times = purchases[(visitor, item)]
    next_index = bisect_right(purchase_times, cutoff)
    expected_label = int(
        next_index < len(purchase_times)
        and purchase_times[next_index] <= label_end
    )
    assert int(row["label"]) == expected_label, (visitor, item, cutoff)

print(f"전체 상품 행: {row_count:,}")
print(f"전체 label=1: {positive_count:,}")
print(f"무작위 행 검증: {len(random_rows):,}개")
print(f"구매 정답 행 검증: {len(positive_rows):,}개")
print("원본 데이터 대조 통과")
