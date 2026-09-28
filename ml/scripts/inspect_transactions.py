from pathlib import Path

import pandas as pd


def main():
    ml_dir = Path(__file__).resolve().parents[1]
    data_path = ml_dir / "data" / "raw" / "events.csv"

    df = pd.read_csv(
        data_path,
        usecols=["visitorid", "event", "itemid", "transactionid"],
        dtype={
            "visitorid": "int64",
            "itemid": "int64",
            "transactionid": "Int64",
        },
    )

    # 분석 대상으로 구매 이벤트만 선택합니다.
    purchases = df.loc[df["event"] == "transaction"]

    if purchases.empty:
        print("구매 기록이 없습니다.")
        return

    if purchases["transactionid"].isna().any():
        raise ValueError("거래번호가 없는 구매 기록을 먼저 확인해야 합니다.")

    # 같은 사용자·거래번호로 묶고, 서로 다른 상품 수를 계산합니다.
    product_counts = (
        purchases.groupby(["visitorid", "transactionid"])["itemid"]
        .nunique()
    )

    total_orders = len(product_counts)
    single_orders = int((product_counts == 1).sum())
    multi_orders = int((product_counts > 1).sum())

    print(f"구매 이벤트 행 수: {len(purchases):,}")
    print(f"거래 수 (사용자·거래번호 기준): {total_orders:,}")
    print(f"상품 1종 구매 거래: {single_orders:,}")
    print(f"상품 2종 이상 구매 거래: {multi_orders:,}")
    print(f"복수 상품 구매 거래 비율: {multi_orders / total_orders:.2%}")

    print("\n=== 거래당 서로 다른 상품 수 ===")
    print(f"평균: {product_counts.mean():.2f}")
    print(f"중앙값: {product_counts.median():.1f}")
    print(f"최대: {product_counts.max()}")

    print("\n=== 상품 종류 수별 거래 수 ===")
    distribution = product_counts.value_counts().sort_index()
    distribution.index.name = "상품 종류 수"
    distribution.name = "거래 수"
    print(distribution.to_string())


if __name__ == "__main__":
    main()