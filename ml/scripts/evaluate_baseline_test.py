import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    log_loss,
    roc_auc_score,
)


FEATURES = [
    "view_count",
    "view_share",
    "seconds_since_first_view",
    "seconds_since_last_view",
]
KEYS = ["session_id", "cutoff_timestamp"]


def main():
    ml_dir = Path(__file__).resolve().parents[1]
    test_path = ml_dir / "data" / "processed" / "splits" / "test.csv"
    artifact_dir = ml_dir / "data" / "artifacts" / "baseline"

    training_report = json.loads(
        (artifact_dir / "metrics.json").read_text(encoding="utf-8")
    )
    if training_report["features"] != FEATURES:
        raise ValueError("학습 때 사용한 피처 순서와 다릅니다.")

    dtypes = {feature: "float32" for feature in FEATURES}
    dtypes.update({
        "session_id": "int32",
        "cutoff_timestamp": "int64",
        "itemid": "int32",
        "label": "int8",
    })
    rows = pd.read_csv(
        test_path,
        usecols=KEYS + ["itemid", "label"] + FEATURES,
        dtype=dtypes,
    )
    if rows.empty or set(rows["label"].unique()) != {0, 1}:
        raise ValueError("평가 데이터에 정답 0과 1이 모두 필요합니다.")
    if not np.isfinite(rows[FEATURES].to_numpy()).all():
        raise ValueError("입력 피처에 결측치 또는 무한대가 있습니다.")

    model = lgb.Booster(
        model_file=str(artifact_dir / "model.txt")
    )
    rows["score"] = model.predict(
        rows[FEATURES],
        num_threads=4,
    )

    train_stats = training_report["split_report"]["stats"]["train"]
    train_purchase_rate = (
        train_stats["positive_rows"] / train_stats["rows"]
    )
    constant_scores = np.full(
        len(rows),
        train_purchase_rate,
    )

    item_metrics = {
        "rows": len(rows),
        "positive_rows": int(rows["label"].sum()),
        "constant_average_precision": float(
            average_precision_score(
                rows["label"], constant_scores
            )
        ),
        "model_average_precision": float(
            average_precision_score(
                rows["label"], rows["score"]
            )
        ),
        "model_roc_auc": float(
            roc_auc_score(rows["label"], rows["score"])
        ),
        "constant_log_loss": float(
            log_loss(rows["label"], constant_scores)
        ),
        "model_log_loss": float(
            log_loss(rows["label"], rows["score"])
        ),
    }

    grouped = rows.groupby(KEYS, sort=False)
    total_snapshots = grouped.ngroups
    candidate_count = grouped["itemid"].transform("size")
    purchase_count = grouped["label"].transform("sum")

    multi_candidate = candidate_count.ge(2)
    multi_snapshots = rows.loc[
        multi_candidate, KEYS
    ].drop_duplicates().shape[0]

    eligible = rows.loc[
        multi_candidate & purchase_count.ge(1)
    ].copy()
    if eligible.empty:
        raise ValueError("순위 평가에 사용할 예측 시점이 없습니다.")

    eligible_groups = eligible.groupby(KEYS, sort=False)
    random_top1 = float(
        eligible_groups["label"].mean().mean()
    )

    max_scores = eligible_groups["score"].transform("max")
    top_rows = eligible.loc[eligible["score"].eq(max_scores)]
    top_groups = top_rows.groupby(KEYS, sort=False)

    ranking_metrics = {
        "total_snapshots": total_snapshots,
        "multi_candidate_snapshots": multi_snapshots,
        "evaluated_snapshots": eligible_groups.ngroups,
        "random_top1": random_top1,
        # 최고 점수 동점자는 그중 무작위 선택으로 계산합니다.
        "model_top1": float(
            top_groups["label"].mean().mean()
        ),
        "top_score_tied_snapshots": int(
            top_groups.size().gt(1).sum()
        ),
    }

    result = {
        "dataset": "test.csv",
        "item_metrics": item_metrics,
        "ranking_metrics": ranking_metrics,
    }
    (artifact_dir / "test_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== 상품별 구매 예측 ===")
    print(f"평가 상품 행: {item_metrics['rows']:,}")
    print(f"구매 정답 행: {item_metrics['positive_rows']:,}")
    print(
        "단순 기준 AP: "
        f"{item_metrics['constant_average_precision']:.6f}"
    )
    print(
        "모델 AP: "
        f"{item_metrics['model_average_precision']:.6f}"
    )
    print(
        "모델 ROC-AUC: "
        f"{item_metrics['model_roc_auc']:.6f}"
    )
    print(
        "단순 기준 Log loss: "
        f"{item_metrics['constant_log_loss']:.6f}"
    )
    print(
        "모델 Log loss: "
        f"{item_metrics['model_log_loss']:.6f}"
    )

    print("\n=== 여러 후보 중 구매 상품을 1순위로 올리기 ===")
    print(f"전체 예측 시점: {total_snapshots:,}")
    print(f"후보 2개 이상: {multi_snapshots:,}")
    print(
        "구매한 후보가 있는 평가 시점: "
        f"{ranking_metrics['evaluated_snapshots']:,}"
    )
    print(
        "무작위 선택: "
        f"{ranking_metrics['random_top1']:.2%}"
    )
    print(
        "모델 1순위: "
        f"{ranking_metrics['model_top1']:.2%}"
    )
    print(
        "최고 점수 동점: "
        f"{ranking_metrics['top_score_tied_snapshots']:,}"
    )


if __name__ == "__main__":
    main()