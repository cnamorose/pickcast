from pathlib import Path

import pandas as pd


VISITOR_ID = 56775
PREDICTION_TIME = "2015-05-07 14:24:01.279+00:00"
SESSION_GAP_MS = 30 * 60 * 1000
LABEL_WINDOW_MS = 30 * 60 * 1000


def main():
    ml_dir = Path(__file__).resolve().parents[2]

    df = pd.read_csv(
        ml_dir / "data" / "raw" / "events.csv",
        usecols=["timestamp", "visitorid", "event", "itemid"],
    )

    cutoff = pd.Timestamp(PREDICTION_TIME).value // 1_000_000
    label_end = cutoff + LABEL_WINDOW_MS

    if label_end > df["timestamp"].max():
        raise ValueError("구매 정답을 확인할 관찰 기간이 부족합니다.")

    user_events = df.loc[df["visitorid"] == VISITOR_ID]

    # 예측 시점까지 발생한 조회만 선택합니다.
    history = (
        user_events.loc[
            user_events["event"].eq("view")
            & user_events["timestamp"].le(cutoff)
        ]
        .sort_values("timestamp", kind="stable")
        .copy()
    )

    if history.empty:
        raise ValueError("예측 시점 이전의 조회 기록이 없습니다.")

    if cutoff - history["timestamp"].iloc[-1] >= SESSION_GAP_MS:
        raise ValueError("예측 시점에 이어지는 조회 세션이 없습니다.")

    # 과거 다른 방문을 제외하고 현재 세션의 조회만 사용합니다.
    gaps = history["timestamp"].diff()
    session_ids = (gaps.isna() | gaps.ge(SESSION_GAP_MS)).cumsum()
    history = history.loc[session_ids.eq(session_ids.iloc[-1])]

    # 상품별 조회 행동을 숫자로 요약합니다.
    features = history.groupby("itemid").agg(
        view_count=("timestamp", "size"),
        first_view=("timestamp", "min"),
        last_view=("timestamp", "max"),
    )

    features["view_share"] = features["view_count"] / len(history)
    features["seconds_since_first_view"] = (
        cutoff - features["first_view"]
    ) / 1000
    features["seconds_since_last_view"] = (
        cutoff - features["last_view"]
    ) / 1000

    features = features.drop(columns=["first_view", "last_view"])

    # 같은 시각의 구매는 선후관계를 확정할 수 없으므로 확인을 요청합니다.
    same_time_purchase = (
        user_events["event"].eq("transaction")
        & user_events["timestamp"].eq(cutoff)
    )
    if same_time_purchase.any():
        raise ValueError("예측과 같은 시각의 구매 기록을 확인해야 합니다.")

    # 구매 정보는 정답을 만드는 데만 사용합니다.
    future_purchases = user_events.loc[
        user_events["event"].eq("transaction")
        & user_events["timestamp"].gt(cutoff)
        & user_events["timestamp"].le(label_end)
    ]

    purchased_items = set(future_purchases["itemid"])
    features["label"] = features.index.isin(purchased_items).astype("int8")
    features = features.reset_index()

    output_dir = ml_dir / "data" / "experiments" / "within_30m" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "sample_training_rows.csv"
    features.to_csv(output_path, index=False)

    print(f"사용자: {VISITOR_ID}")
    print(f"예측 시점: {PREDICTION_TIME}")
    print(f"입력에 사용한 조회 수: {len(history)}")
    print(f"후보 상품 수: {len(features)}")
    print("\n=== 학습용 표 예제 ===")
    print(features.to_string(index=False, float_format="%.3f"))
    print(f"\n저장 위치: {output_path}")


if __name__ == "__main__":
    main()
