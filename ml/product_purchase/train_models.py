"""기준선과 LightGBM을 학습하고 valid로 비교한다.

- 단순 구매 비율: 모든 후보에 train 구매 비율을 준다.
- 로지스틱 회귀: 예측 시점 가중치(point)로 학습한다.
- LightGBM: 행 가중치 방식(row, point, user)마다 학습한다.

train은 샘플링하지 않고 전체 행을 사용한다. valid는 실제 분포 그대로 평가한다.
확률 보정은 다음 단계에서 하므로 여기의 Log loss·Brier는 참고용이다.
"""
import argparse
import json
from time import perf_counter

import joblib
import lightgbm as lgb
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from features import FEATURES
from modeling import (
    WEIGHTINGS,
    evaluate,
    load_split,
    log_features,
    models_dir,
    row_weights,
    summary_line,
)


PARAMS = {
    "objective": "binary",
    "metric": "average_precision",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 1000,
    "lambda_l2": 1.0,
    "verbosity": -1,
    "seed": 42,
}
MAX_ROUNDS = 3000
EARLY_STOPPING = 100


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weightings", nargs="+", default=WEIGHTINGS, choices=WEIGHTINGS)
    parser.add_argument("--skip-baselines", action="store_true")
    args = parser.parse_args()

    models_dir.mkdir(parents=True, exist_ok=True)
    report_path = models_dir / "validation_metrics.json"
    report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.exists()
        else {"models": {}}
    )

    print("train/valid를 읽습니다.", flush=True)
    train = load_split("train")
    valid = load_split("valid")
    y_train = train["label"].to_numpy()
    valid_point_weight = 1.0 / valid["candidate_count"].to_numpy(dtype=np.float64)
    print(f"train {len(train):,}행 / valid {len(valid):,}행", flush=True)

    if not args.skip_baselines:
        rate = float(y_train.mean())
        result = evaluate(valid, np.full(len(valid), rate))
        report["models"]["constant"] = {"train_positive_rate": rate, "valid": result}
        print(summary_line("constant", result), flush=True)

        started = perf_counter()
        logistic = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        x_train = log_features(train)
        logistic.fit(
            x_train,
            y_train,
            logisticregression__sample_weight=row_weights(train, "point"),
        )
        del x_train
        p_valid = logistic.predict_proba(log_features(valid))[:, 1]
        result = evaluate(valid, p_valid)
        joblib.dump(logistic, models_dir / "logistic_point.joblib")
        report["models"]["logistic_point"] = {
            "weighting": "point",
            "coefficients": dict(
                zip(FEATURES, logistic[-1].coef_[0].round(4).tolist())
            ),
            "train_seconds": round(perf_counter() - started, 1),
            "valid": result,
        }
        print(summary_line("logistic_point", result), flush=True)

    valid_set = lgb.Dataset(
        valid[FEATURES], valid["label"], weight=valid_point_weight, free_raw_data=False
    )
    for weighting in args.weightings:
        started = perf_counter()
        train_set = lgb.Dataset(
            train[FEATURES], y_train, weight=row_weights(train, weighting)
        )
        model = lgb.train(
            PARAMS,
            train_set,
            num_boost_round=MAX_ROUNDS,
            valid_sets=[valid_set],
            valid_names=["valid"],
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING, verbose=False),
                lgb.log_evaluation(100),
            ],
        )
        del train_set
        name = f"lgbm_{weighting}"
        model.save_model(models_dir / f"{name}.txt", num_iteration=model.best_iteration)
        p_valid = model.predict(valid[FEATURES], num_iteration=model.best_iteration)
        result = evaluate(valid, p_valid)
        importance = model.feature_importance("gain")
        report["models"][name] = {
            "weighting": weighting,
            "params": PARAMS,
            "best_iteration": model.best_iteration,
            "train_seconds": round(perf_counter() - started, 1),
            "feature_importance_gain": dict(
                zip(FEATURES, (importance / importance.sum()).round(4).tolist())
            ),
            "valid": result,
        }
        print(summary_line(name, result), flush=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 최종 모델 선택은 이 결과를 비교해 calibrate_model.py의 SELECTED_MODEL에 기록한다.
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
