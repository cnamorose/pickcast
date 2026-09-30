import json
from pathlib import Path

import pandas as pd
from tqdm import tqdm


CHUNK_SIZE = 200_000


def utc_text(timestamp):
    return str(pd.to_datetime(int(timestamp), unit="ms", utc=True))


def main():
    ml_dir = Path(__file__).resolve().parents[2]
    source = ml_dir / "data" / "experiments" / "within_30m" / "processed" / "training_rows.csv"
    output_dir = ml_dir / "data" / "experiments" / "within_30m" / "processed" / "splits"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("세션별 예측 시점과 구매 관찰 기간을 확인합니다.")

    metadata = pd.read_csv(
        source,
        usecols=[
            "session_id",
            "cutoff_timestamp",
            "label_end_timestamp",
        ],
    )
    if metadata.empty:
        raise ValueError("학습용 데이터가 비어 있습니다.")

    total_rows = len(metadata)
    sessions = metadata.groupby("session_id").agg(
        first_cutoff=("cutoff_timestamp", "min"),
        last_cutoff=("cutoff_timestamp", "max"),
        label_end=("label_end_timestamp", "max"),
        snapshots=("cutoff_timestamp", "nunique"),
    )
    del metadata

    start = int(sessions["first_cutoff"].min())
    end = int(sessions["last_cutoff"].max())
    if start == end:
        raise ValueError("시간순으로 나누기에는 데이터 기간이 부족합니다.")

    # 예측 시점의 전체 시간 범위를 기준으로 경계를 고정합니다.
    valid_start = start + (end - start) * 70 // 100
    test_start = start + (end - start) * 85 // 100

    # 한 세션에 하나의 구간만 배정합니다.
    sessions["split"] = "excluded"

    train_mask = sessions["label_end"].lt(valid_start)
    valid_mask = (
        sessions["first_cutoff"].ge(valid_start)
        & sessions["label_end"].lt(test_start)
    )
    test_mask = sessions["first_cutoff"].ge(test_start)

    sessions.loc[train_mask, "split"] = "train"
    sessions.loc[valid_mask, "split"] = "valid"
    sessions.loc[test_mask, "split"] = "test"

    names = ("train", "valid", "test")
    for name in names:
        if not sessions["split"].eq(name).any():
            raise ValueError(f"{name} 구간에 배정된 세션이 없습니다.")

    print(f"검증 시작 시각: {utc_text(valid_start)}")
    print(f"평가 시작 시각: {utc_text(test_start)}")

    stats = {}
    for name in (*names, "excluded"):
        selected = sessions.loc[sessions["split"].eq(name)]
        stats[name] = {
            "sessions": len(selected),
            "snapshots": int(selected["snapshots"].sum()),
            "rows": 0,
            "positive_rows": 0,
        }

    # 중단되면 임시 파일만 남고, 재실행 시 처음부터 작성합니다.
    columns = pd.read_csv(source, nrows=0).columns
    temp_paths = {
        name: output_dir / f"{name}.csv.tmp"
        for name in names
    }
    for path in temp_paths.values():
        pd.DataFrame(columns=columns).to_csv(path, index=False)

    with tqdm(
        total=total_rows,
        desc="시간순 데이터 분리",
        unit="row",
    ) as progress:
        for chunk in pd.read_csv(source, chunksize=CHUNK_SIZE):
            assignments = chunk["session_id"].map(sessions["split"])
            if assignments.isna().any():
                raise ValueError("구간을 배정하지 못한 세션이 있습니다.")

            # 저장 전에 시간 경계를 다시 확인합니다.
            train = chunk.loc[assignments.eq("train")]
            valid = chunk.loc[assignments.eq("valid")]
            test = chunk.loc[assignments.eq("test")]

            if not train["label_end_timestamp"].lt(valid_start).all():
                raise ValueError("학습 데이터가 검증 기간을 침범했습니다.")
            if not (
                valid["cutoff_timestamp"].ge(valid_start).all()
                and valid["label_end_timestamp"].lt(test_start).all()
            ):
                raise ValueError("검증 데이터의 시간 경계가 잘못됐습니다.")
            if not test["cutoff_timestamp"].ge(test_start).all():
                raise ValueError("평가 데이터의 시간 경계가 잘못됐습니다.")

            for name in (*names, "excluded"):
                part = chunk.loc[assignments.eq(name)]
                stats[name]["rows"] += len(part)
                stats[name]["positive_rows"] += int(part["label"].sum())

                if name in names and not part.empty:
                    part.to_csv(
                        temp_paths[name],
                        mode="a",
                        header=False,
                        index=False,
                    )

            progress.update(len(chunk))

    if sum(item["rows"] for item in stats.values()) != total_rows:
        raise ValueError("분리 전후의 행 수가 일치하지 않습니다.")

    for name in names:
        temp_paths[name].replace(output_dir / f"{name}.csv")

    report = {
        "source": source.name,
        "split_basis": "예측 시점의 시간 범위 기준 70/15/15",
        "valid_start_utc": utc_text(valid_start),
        "test_start_utc": utc_text(test_start),
        "stats": stats,
    }
    (output_dir / "split_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== 분리 결과 ===")
    for name, values in stats.items():
        print(
            f"{name}: 세션 {values['sessions']:,}개 / "
            f"예측 시점 {values['snapshots']:,}개 / "
            f"상품 행 {values['rows']:,}개 / "
            f"구매 정답 {values['positive_rows']:,}행"
        )
    print(f"\n저장 위치: {output_dir}")


if __name__ == "__main__":
    main()
