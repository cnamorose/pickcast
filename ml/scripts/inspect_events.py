from pathlib import Path

import pandas as pd


def main():
    ml_dir = Path(__file__).resolve().parents[1]
    data_path = ml_dir / "data" / "raw" / "events.csv"

    df = pd.read_csv(data_path)

    print("=== 데이터 크기 ===")
    print(f"행: {len(df):,}개 / 열: {len(df.columns)}개")

    print("\n=== 처음 5개 행 ===")
    print(df.head().to_string(index=False))

    print("\n=== 컬럼별 자료형 ===")
    print(df.dtypes)

    print("\n=== 이벤트별 개수 ===")
    print(df["event"].value_counts(dropna=False))

    print("\n=== 컬럼별 결측치 개수 ===")
    print(df.isna().sum())

    print("\n=== 완전히 동일한 중복 행 개수 ===")
    print(df.duplicated().sum())


if __name__ == "__main__":
    main()