"""생성한 학습 데이터를 원본 이벤트에서 직접 다시 계산한 값과 비교한다.

- 사용자 분리: 한 사용자의 행이 배정된 구간에만 있는지
- 예측 시점: 샘플 시점의 후보 목록이 "그때까지 조회했고 아직 구매하지 않은 상품"과 같은지
- 피처와 정답: 샘플 행의 값이 원본에서 다시 계산한 값과 같은지
"""
import random

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from events import first_purchase_times, load_events, output_dir, sorted_views
from features import FEATURES


SEED = 123
POINTS_PER_SPLIT = 300
failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


def expected_rows(user_views, first_buy, visitor, now):
    """원본 조회를 처음부터 다시 훑어 now 시점의 후보별 피처와 정답을 계산한다."""
    seen = user_views[user_views["timestamp"] <= now].copy()
    previous = seen["itemid"].shift()
    seen["revisit"] = (seen["itemid"] != previous) & seen["itemid"].duplicated()
    grouped = seen.groupby("itemid")
    stats = pd.DataFrame(
        {
            "view_count": grouped.size(),
            "first": grouped["timestamp"].min(),
            "last": grouped["timestamp"].max(),
            "revisit_count": grouped["revisit"].sum(),
        }
    )
    rows = {}
    for item, s in stats.iterrows():
        buy = first_buy.get((visitor, item))
        if buy is not None and buy <= now:
            continue
        rows[item] = {
            "view_count": s["view_count"],
            "view_share": s["view_count"] / len(seen),
            "seconds_since_first_view": (now - s["first"]) / 1000,
            "seconds_since_last_view": (now - s["last"]) / 1000,
            "revisit_count": s["revisit_count"],
            "user_total_views": len(seen),
            "distinct_items_viewed": len(stats),
            "is_last_viewed": int(s["last"] == seen["timestamp"].max()),
            "label": int(buy is not None),
        }
    return rows


def main():
    print("이벤트를 읽습니다.", flush=True)
    events, _ = load_events()
    views = sorted_views(events)
    first_buy = first_purchase_times(events).to_dict()
    purchase_times = set(
        zip(
            events.loc[events["event"] == "transaction", "visitorid"],
            events.loc[events["event"] == "transaction", "timestamp"],
        )
    )
    users = pd.read_parquet(output_dir / "users.parquet").set_index("visitorid")
    rng = random.Random(SEED)

    total_rows = 0
    total_positives = 0
    for split in ("train", "valid", "test"):
        path = output_dir / "training_rows" / f"{split}.parquet"
        print(f"{split}를 확인합니다.", flush=True)

        keys = pq.read_table(
            path, columns=["visitorid", "cutoff_timestamp", "label"]
        ).to_pandas()
        total_rows += len(keys)
        total_positives += int(keys["label"].sum())

        split_users = keys["visitorid"].unique()
        wrong = users.loc[split_users, "split"].astype(str) != split
        check(not wrong.any(), f"{split}: 다른 구간에 배정된 사용자 {wrong.sum()}명")

        per_user = keys.groupby("visitorid").size()
        mismatch = per_user != users.loc[per_user.index, "n_rows"]
        check(not mismatch.any(), f"{split}: users.parquet 행 수 불일치 {mismatch.sum()}명")

        same_time = [
            (v, t)
            for v, t in keys[["visitorid", "cutoff_timestamp"]]
            .drop_duplicates()
            .itertuples(index=False)
            if (v, t) in purchase_times
        ]
        check(not same_time, f"{split}: 같은 시각 구매가 있는 예측 시점 {len(same_time)}개")

        # 무작위 시점, 정답 1이 있는 시점, 과다 조회 사용자의 시점을 고루 뽑는다.
        points = keys[["visitorid", "cutoff_timestamp"]].drop_duplicates()
        positive_points = keys.loc[
            keys["label"] == 1, ["visitorid", "cutoff_timestamp"]
        ].drop_duplicates()
        heavy_points = points[
            users.loc[points["visitorid"], "heavy_user"].to_numpy() == 1
        ]
        sample = pd.concat(
            [
                points.sample(POINTS_PER_SPLIT, random_state=rng.randrange(10**6)),
                positive_points.sample(
                    min(POINTS_PER_SPLIT, len(positive_points)),
                    random_state=rng.randrange(10**6),
                ),
                heavy_points.sample(
                    min(POINTS_PER_SPLIT // 3, len(heavy_points)),
                    random_state=rng.randrange(10**6),
                ),
            ]
        ).drop_duplicates()
        del keys, points, positive_points, heavy_points

        dataset = ds.dataset(path)
        sampled = dataset.to_table(
            filter=pc.field("visitorid").isin(sample["visitorid"].unique())
            & pc.field("cutoff_timestamp").isin(sample["cutoff_timestamp"].unique())
        ).to_pandas()
        sampled = sampled.merge(sample, on=["visitorid", "cutoff_timestamp"])
        views_by_user = {
            v: g for v, g in views[views["visitorid"].isin(sample["visitorid"])].groupby(
                "visitorid"
            )
        }

        checked_rows = 0
        for (visitor, now), actual in sampled.groupby(["visitorid", "cutoff_timestamp"]):
            expected = expected_rows(views_by_user[visitor], first_buy, visitor, now)
            actual = actual.set_index("itemid")
            check(
                set(actual.index) == set(expected),
                f"{split}: 후보 불일치 visitor={visitor} t={now}",
            )
            for item, values in expected.items():
                if item not in actual.index:
                    continue
                row = actual.loc[item]
                for name in [*FEATURES, "label"]:
                    check(
                        np.isclose(row[name], values[name], rtol=1e-6, atol=1.0)
                        if name.startswith("seconds")
                        else np.isclose(row[name], values[name], rtol=1e-6),
                        f"{split}: {name} 불일치 visitor={visitor} t={now} item={item} "
                        f"({row[name]} != {values[name]})",
                    )
                checked_rows += 1
        print(f"  시점 {len(sample):,}개 / 행 {checked_rows:,}개 대조", flush=True)

    # 조회 뒤 구매한 사용자·상품 쌍은 모두 정답 1 행을 하나 이상 가져야 한다.
    first_view = views.groupby(["visitorid", "itemid"])["timestamp"].min()
    pairs = pd.concat(
        [first_view.rename("view"), first_purchase_times(events).rename("buy")],
        axis=1,
        join="inner",
    )
    expected_pairs = pairs[pairs["view"] < pairs["buy"]]
    buyers_rows = users.loc[
        expected_pairs.index.get_level_values("visitorid").unique(), "n_positive_rows"
    ]
    check((buyers_rows > 0).all(), f"정답 1 행이 없는 구매 사용자 {(buyers_rows == 0).sum()}명")
    check(
        total_positives == int(users["n_positive_rows"].sum()),
        "정답 1 행 수가 users.parquet 합계와 다름",
    )

    print(f"전체 행 {total_rows:,}개 / 정답 1 {total_positives:,}개")
    if failures:
        print(f"실패 {len(failures)}건")
        for message in failures[:30]:
            print(" -", message)
        raise SystemExit(1)
    print("모든 검증을 통과했습니다.")


if __name__ == "__main__":
    main()
