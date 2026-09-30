import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd


FEATURES = [
    "view_count",
    "view_share",
    "seconds_since_first_view",
    "seconds_since_last_view",
]
KEYS = ["session_id", "cutoff_timestamp"]


def main():
    ml_dir = Path(__file__).resolve().parents[2]
    valid_path = ml_dir / "data" / "experiments" / "within_30m" / "processed" / "splits" / "valid.csv"
    artifact_dir = ml_dir / "data" / "experiments" / "within_30m" / "artifacts"
    model_path = artifact_dir / "model.txt"

    dtypes = {feature: "float32" for feature in FEATURES}
    dtypes.update({
        "session_id": "int32",
        "cutoff_timestamp": "int64",
        "itemid": "int32",
        "label": "int8",
    })
    rows = pd.read_csv(
        valid_path,
        usecols=KEYS + ["itemid", "label"] + FEATURES,
        dtype=dtypes,
    )

    grouped = rows.groupby(KEYS, sort=False)
    total_snapshots = grouped.ngroups
    candidate_count = grouped["itemid"].transform("size")
    purchase_count = grouped["label"].transform("sum")

    multi_candidate = candidate_count.ge(2)
    eligible_mask = multi_candidate & purchase_count.ge(1)

    multi_snapshots = rows.loc[
        multi_candidate, KEYS
    ].drop_duplicates().shape[0]

    eligible = rows.loc[eligible_mask].copy()
    if eligible.empty:
        raise ValueError("평가할 예측 시점이 없습니다.")

    eligible_groups = eligible.groupby(KEYS, sort=False)
    eligible_snapshots = eligible_groups.ngroups

    model = lgb.Booster(model_file=str(model_path))
    eligible["score"] = model.predict(
        eligible[FEATURES],
        num_threads=4,
    )
    if not np.isfinite(eligible["score"]).all():
        raise ValueError("모델 점수에 유효하지 않은 값이 있습니다.")

    # 무작위로 후보 하나를 고를 때의 기대 성공률입니다.
    random_top1 = float(
        eligible.groupby(KEYS, sort=False)["label"].mean().mean()
    )

    # 최고 점수 동점자는 그중 무작위로 하나를 고른 것으로 계산합니다.
    max_scores = eligible.groupby(
        KEYS, sort=False
    )["score"].transform("max")
    top_rows = eligible.loc[eligible["score"].eq(max_scores)]
    top_groups = top_rows.groupby(KEYS, sort=False)

    model_top1 = float(top_groups["label"].mean().mean())
    tied_snapshots = int(top_groups.size().gt(1).sum())

    report = {
        "dataset": "valid.csv",
        "total_snapshots": total_snapshots,
        "multi_candidate_snapshots": multi_snapshots,
        "evaluated_snapshots": eligible_snapshots,
        "random_top1": random_top1,
        "model_top1": model_top1,
        "top_score_tied_snapshots": tied_snapshots,
        "note": (
            "후보가 2개 이상이고 이후 30분 내 구매한 후보가 "
            "1개 이상인 예측 시점만 평가"
        ),
    }
    (artifact_dir / "ranking_valid.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"검증 예측 시점: {total_snapshots:,}개")
    print(f"후보 2개 이상: {multi_snapshots:,}개")
    print(f"이번 순위 평가에 사용: {eligible_snapshots:,}개")
    print(f"최고 점수 동점: {tied_snapshots:,}개")
    print(f"\n무작위 선택 시 정답 확률: {random_top1:.2%}")
    print(f"모델 1순위 정답 확률: {model_top1:.2%}")


if __name__ == "__main__":
    main()
