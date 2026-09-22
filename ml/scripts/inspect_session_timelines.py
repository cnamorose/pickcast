from pathlib import Path

import pandas as pd


GAP_MS = 30 * 60 * 1000


def main():
    ml_dir = Path(__file__).resolve().parents[1]
    df = pd.read_csv(
        ml_dir / "data" / "raw" / "events.csv",
        dtype={"transactionid": "Int64"},
    )
    data_end = df["timestamp"].max()

    # 조회 행동만으로 세션을 나눕니다.
    views = (
        df.loc[df["event"] == "view"]
        .sort_values(["visitorid", "timestamp"], kind="stable")
        .copy()
    )
    gaps = views.groupby("visitorid")["timestamp"].diff()
    views["session_id"] = (gaps.isna() | gaps.ge(GAP_MS)).cumsum()

    purchases = df.loc[df["event"] == "transaction"].copy()

    # 구매를 같은 사용자의 가장 최근 조회에 연결합니다.
    # 세션 경계와 맞추기 위해 정확히 30분 차이는 제외합니다.
    lookup = views[
        ["timestamp", "visitorid", "session_id"]
    ].rename(columns={"timestamp": "previous_view_time"})

    linked = pd.merge_asof(
        purchases.sort_values("timestamp"),
        lookup.sort_values("previous_view_time"),
        left_on="timestamp",
        right_on="previous_view_time",
        by="visitorid",
        direction="backward",
        tolerance=GAP_MS - 1,
    )

    unmatched = int(linked["session_id"].isna().sum())
    linked = linked.dropna(subset=["session_id"]).copy()
    linked["session_id"] = linked["session_id"].astype("int64")

    sessions = views.groupby("session_id").agg(
        view_count=("itemid", "size"),
        viewed_items=("itemid", "nunique"),
        last_view=("timestamp", "max"),
    )

    purchase_stats = linked.groupby("session_id").agg(
        purchase_rows=("itemid", "size"),
        purchased_items=("itemid", "nunique"),
        first_purchase=("timestamp", "min"),
    )
    sessions = sessions.join(purchase_stats)

    for column in ["purchase_rows", "purchased_items"]:
        sessions[column] = sessions[column].fillna(0).astype("int64")

    # 파일 종료 직전의 세션은 관찰 시간이 부족하므로 예시에서 제외합니다.
    complete = sessions["last_view"] + GAP_MS <= data_end

    print(f"전체 조회 세션 수: {len(sessions):,}")
    print(f"관찰 시간 부족으로 예시에서 제외: {(~complete).sum():,}")
    print(f"직전 30분 내 조회에 연결되지 않은 구매 행: {unmatched:,}")

    # 읽기 쉬운 예시를 위해 여러 상품을 조회했고,
    # 조회·구매를 합쳐 20행 이하인 세션에서 선택합니다.
    examples = sessions.loc[
        complete
        & sessions["viewed_items"].ge(2)
        & (sessions["view_count"] + sessions["purchase_rows"]).le(20)
    ]

    cases = [
        ("구매 기록 없음", examples["purchased_items"].eq(0)),
        ("상품 한 종류 구매", examples["purchased_items"].eq(1)),
        ("여러 종류의 상품 구매", examples["purchased_items"].ge(2)),
        (
            "구매 후에도 조회가 이어짐",
            examples["last_view"].gt(examples["first_purchase"]),
        ),
    ]

    for title, condition in cases:
        pool = examples.loc[condition]
        print(f"\n=== {title} ===")

        if pool.empty:
            print("현재 예시 조건에 해당하는 세션이 없습니다.")
            continue

        session_id = pool.sample(n=1, random_state=42).index[0]

        timeline = pd.concat(
            [
                views.loc[views["session_id"] == session_id],
                linked.loc[linked["session_id"] == session_id],
            ],
            ignore_index=True,
        ).sort_values("timestamp", kind="stable")

        timeline["time_utc"] = (
            pd.to_datetime(timeline["timestamp"], unit="ms", utc=True)
            .dt.strftime("%Y-%m-%d %H:%M:%S.%f")
            .str[:-3]
        )

        visitor_id = int(timeline["visitorid"].iloc[0])
        print(f"사용자: {visitor_id} / 세션: {session_id}")
        print(
            timeline[
                ["time_utc", "event", "itemid", "transactionid"]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()