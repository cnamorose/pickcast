import json
from pathlib import Path
from time import perf_counter

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)


FEATURES = [
    "view_count",
    "view_share",
    "seconds_since_first_view",
    "seconds_since_last_view",
    "views_last_day",
]

PARAMS = {
    "objective": "binary",
    "metric": "average_precision",
    "n_estimators": 1000,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 100,
    "random_state": 42,
    "n_jobs": 4,
    "deterministic": True,
    "force_col_wise": True,
    "verbosity": -1,
}


def load_data(path):
    dtypes = {feature: "float32" for feature in FEATURES}
    dtypes["label"] = "int8"

    frame = pd.read_csv(
        path,
        usecols=FEATURES + ["label"],
        dtype=dtypes,
    )
    if frame.empty:
        raise ValueError(f"{path.name}: 데이터가 비어 있습니다.")
    if not np.isfinite(frame[FEATURES].to_numpy()).all():
        raise ValueError(f"{path.name}: 피처에 결측치 또는 무한대가 있습니다.")
    if set(frame["label"].unique()) != {0, 1}:
        raise ValueError(f"{path.name}: 정답 0과 1이 모두 필요합니다.")

    return frame[FEATURES], frame["label"]


def main():
    ml_dir = Path(__file__).resolve().parents[1]
    split_dir = ml_dir / "data" / "processed" / "product_purchase_v2" / "splits"
    output_dir = ml_dir / "data" / "artifacts" / "product_purchase_recent_day"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("학습 데이터를 읽습니다.", flush=True)
    x_train, y_train = load_data(split_dir / "train.csv")
    print("검증 데이터를 읽습니다.", flush=True)
    x_valid, y_valid = load_data(split_dir / "valid.csv")

    print(f"학습 상품 행: {len(y_train):,}")
    print(f"검증 상품 행: {len(y_valid):,}")
    print(f"학습 구매 비율: {y_train.mean():.4%}")
    print(f"검증 구매 비율: {y_valid.mean():.4%}")

    model = lgb.LGBMClassifier(**PARAMS)

    print("\n학습 시작: 25회마다 검증 AP를 출력합니다.", flush=True)
    started = perf_counter()
    model.fit(
        x_train,
        y_train,
        eval_X=x_valid,
        eval_y=y_valid,
        eval_names=["valid"],
        callbacks=[
            lgb.log_evaluation(period=25),
            lgb.early_stopping(
                stopping_rounds=50,
                first_metric_only=True,
            ),
        ],
    )
    training_seconds = perf_counter() - started

    probabilities = model.predict_proba(
        x_valid,
        num_iteration=model.best_iteration_,
    )[:, 1]
    constant = np.full(len(y_valid), float(y_train.mean()))

    metrics = {
        "average_precision": float(
            average_precision_score(y_valid, probabilities)
        ),
        "roc_auc": float(roc_auc_score(y_valid, probabilities)),
        "log_loss": float(log_loss(y_valid, probabilities)),
        "brier_score": float(brier_score_loss(y_valid, probabilities)),
    }
    reference = {
        "average_precision": float(
            average_precision_score(y_valid, constant)
        ),
        "log_loss": float(log_loss(y_valid, constant)),
        "brier_score": float(brier_score_loss(y_valid, constant)),
    }

    model_path = output_dir / "model.txt"
    model.booster_.save_model(
        str(model_path),
        num_iteration=model.best_iteration_,
    )

    report = {
        "target": "예측 시점 이후 24시간 내 동일 사용자·상품 구매",
        "features": FEATURES,
        "parameters": PARAMS,
        "train_rows": len(y_train),
        "valid_rows": len(y_valid),
        "best_iteration": int(model.best_iteration_),
        "training_seconds": training_seconds,
        "validation_metrics": metrics,
        "constant_reference": reference,
    }
    (output_dir / "validation_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== 검증 결과 ===")
    print(f"학습 소요 시간: {training_seconds:.1f}초")
    print(f"선택된 학습 반복 수: {model.best_iteration_:,}")
    print(f"단순 기준 AP: {reference['average_precision']:.6f}")
    print(f"모델 AP: {metrics['average_precision']:.6f}")
    print(f"모델 ROC-AUC: {metrics['roc_auc']:.6f}")
    print(f"단순 기준 Log loss: {reference['log_loss']:.6f}")
    print(f"모델 Log loss: {metrics['log_loss']:.6f}")
    print(f"모델 저장 위치: {model_path}")
    print("calibration과 test 데이터는 사용하지 않았습니다.")


if __name__ == "__main__":
    main()
