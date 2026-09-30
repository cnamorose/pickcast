from pathlib import Path

import numpy as np
import pandas as pd


SESSION_GAP_MS = 30 * 60 * 1000
LABEL_WINDOW_MS = 30 * 60 * 1000

FEATURE_COLUMNS = [
    "view_count",
    "view_share",
    "seconds_since_first_view",
    "seconds_since_last_view",
    "label",
]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    ml_dir = Path(__file__).resolve().parents[2]
    rows = pd.read_csv(
        ml_dir / "data" / "experiments" / "within_30m" / "processed" / "training_rows_sample.csv"
    )
    raw = pd.read_csv(
        ml_dir / "data" / "raw" / "events.csv",
        usecols=["timestamp", "visitorid", "event", "itemid"],
    )
    data_end = int(raw["timestamp"].max())

    # 표 자체의 기본 조건을 확인합니다.
    check(not rows.empty, "생성된 표가 비어 있습니다.")
    check(not rows.isna().any().any(), "결측치가 있습니다.")
    check(
        not rows.duplicated(
            ["visitorid", "cutoff_timestamp", "itemid"]
        ).any(),
        "같은 예측 시점에 동일 상품 행이 중복됐습니다.",
    )
    check(rows["label"].isin([0, 1]).all(), "정답은 0 또는 1이어야 합니다.")
    check(
        (
            rows["view_count"].ge(1)
            & rows["view_count"].mod(1).eq(0)
        ).all(),
        "조회 횟수는 1 이상의 정수여야 합니다.",
    )
    check(
        rows[
            ["seconds_since_first_view", "seconds_since_last_view"]
        ].ge(0).all().all(),
        "경과 시간이 음수입니다.",
    )
    check(
        rows.groupby("session_id")["visitorid"].nunique().eq(1).all(),
        "하나의 세션에 여러 사용자가 섞였습니다.",
    )

    share_sums = rows.groupby(
        ["visitorid", "cutoff_timestamp"]
    )["view_share"].sum()
    check(
        np.isclose(share_sums, 1.0).all(),
        "예측 시점별 조회 비율의 합이 1이 아닙니다.",
    )
    print("기본 조건 검증 통과")

    # 표에 포함된 사용자의 원본 기록을 준비합니다.
    users = {
        int(visitor): events.sort_values("timestamp", kind="stable")
        for visitor, events in raw.loc[
            raw["visitorid"].isin(rows["visitorid"])
        ].groupby("visitorid")
    }

    checked = 0
    for (visitor, cutoff), actual in rows.groupby(
        ["visitorid", "cutoff_timestamp"]
    ):
        context = f"사용자={visitor}, 예측 시점={cutoff}"
        events = users[int(visitor)]
        label_end = cutoff + LABEL_WINDOW_MS

        check(
            actual["session_id"].nunique() == 1,
            f"{context}: 같은 예측 시점의 세션 번호가 다릅니다.",
        )
        check(
            actual["label_end_timestamp"].eq(label_end).all()
            and label_end <= data_end,
            f"{context}: 구매 관찰 기간이 잘못됐습니다.",
        )

        # 예측 시점까지의 조회에서 현재 세션만 복원합니다.
        history = events.loc[
            events["event"].eq("view")
            & events["timestamp"].le(cutoff)
        ].copy()
        check(
            not history.empty
            and history["timestamp"].iloc[-1] == cutoff,
            f"{context}: 예측 시점에 조회 기록이 없습니다.",
        )
        gaps = history["timestamp"].diff()
        starts = gaps.isna() | gaps.ge(SESSION_GAP_MS)
        session_start = history.loc[starts, "timestamp"].iloc[-1]
        history = history.loc[
            history["timestamp"].ge(session_start)
        ]

        expected = history.groupby("itemid").agg(
            view_count=("timestamp", "size"),
            first_view=("timestamp", "min"),
            last_view=("timestamp", "max"),
        )
        expected["view_share"] = expected["view_count"] / len(history)
        expected["seconds_since_first_view"] = (
            cutoff - expected["first_view"]
        ) / 1000
        expected["seconds_since_last_view"] = (
            cutoff - expected["last_view"]
        ) / 1000

        purchases = events.loc[events["event"].eq("transaction")]
        check(
            not purchases["timestamp"].eq(cutoff).any(),
            f"{context}: 같은 시각의 구매가 있는 예제입니다.",
        )
        future_items = purchases.loc[
            purchases["timestamp"].gt(cutoff)
            & purchases["timestamp"].le(label_end),
            "itemid",
        ]
        expected["label"] = expected.index.isin(future_items).astype(int)

        try:
            pd.testing.assert_frame_equal(
                actual.set_index("itemid")[FEATURE_COLUMNS].sort_index(),
                expected[FEATURE_COLUMNS].sort_index(),
                check_dtype=False,
                check_exact=False,
                rtol=1e-9,
                atol=1e-9,
            )
        except AssertionError as error:
            raise ValueError(
                f"{context}: 원본과 후보·피처·정답이 다릅니다.\n{error}"
            ) from error

        checked += 1

    print(f"원본 대조 통과: 예측 시점 {checked:,}개")
    print(f"검증한 상품 행: {len(rows):,}개")
    print("검증 완료")


if __name__ == "__main__":
    main()
