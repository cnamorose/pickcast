"""선택한 모델의 점수를 valid에서 확률로 보정하고 구매 판정 임계값을 정한다.

보정 방식은 valid를 사용자 단위 5개 묶음으로 나눈 교차 보정으로 고른다.
isotonic은 확률이 계단식이라 조회해도 확률이 바뀌지 않는 구간이 생기므로 비교용으로만
기록하고, 연속적인 platt와 isotonic_smooth 중에서 Log loss가 낮은 쪽을 선택한다.
임계값도 교차 보정 확률에서 정해, 보정에 쓴 행으로 바로 평가하지 않는다.
test는 사용하지 않는다.
"""
import json

import lightgbm as lgb
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from features import FEATURES
from modeling import (
    apply_calibration,
    best_f1_threshold,
    evaluate,
    load_split,
    models_dir,
    point_weights,
    reliability_by_edges,
    reliability_table,
)


# 세 가중치 방식의 valid 시점 가중 AP 차이가 0.0002로 작아, 과다 조회 제외 AP와
# 과다 조회 사용자 AP가 가장 높은 point 가중치 모델을 선택했다.
SELECTED_MODEL = "lgbm_point"
FOLDS = 5
METHODS = ["platt", "isotonic", "isotonic_smooth"]
CANDIDATES = ["platt", "isotonic_smooth"]
RELIABILITY_EDGES = [0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.1, 0.2, 1]


def fit_calibration(method, raw, y, weight):
    if method == "platt":
        raw = np.clip(raw, 1e-12, 1 - 1e-12)
        logit = np.log(raw / (1 - raw)).reshape(-1, 1)
        model = LogisticRegression(C=1e6).fit(logit, y, sample_weight=weight)
        return {
            "method": "platt",
            "slope": float(model.coef_[0, 0]),
            "intercept": float(model.intercept_[0]),
        }
    model = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(
        raw, y, sample_weight=weight
    )
    if method == "isotonic_smooth":
        # 같은 확률을 갖는 계단마다 로짓 공간의 중간점을 잡고, 중간점끼리 직선으로 잇는다.
        x = np.clip(model.X_thresholds_, 1e-12, 1 - 1e-12)
        x_logit = np.log(x / (1 - x))
        y_steps = model.y_thresholds_
        step_start = np.r_[True, y_steps[1:] != y_steps[:-1]]
        step_id = np.cumsum(step_start) - 1
        centers = [
            (x_logit[step_id == k].min() + x_logit[step_id == k].max()) / 2
            for k in range(step_id[-1] + 1)
        ]
        return {
            "method": "isotonic_smooth",
            "x_logit": [float(c) for c in centers],
            "y": y_steps[step_start].tolist(),
        }
    return {
        "method": "isotonic",
        "x": model.X_thresholds_.tolist(),
        "y": model.y_thresholds_.tolist(),
    }


def main():
    print("valid를 읽고 모델 점수를 계산합니다.", flush=True)
    valid = load_split("valid")
    model = lgb.Booster(model_file=str(models_dir / f"{SELECTED_MODEL}.txt"))
    raw = model.predict(valid[FEATURES])
    y = valid["label"].to_numpy()
    weight = point_weights(valid)

    # 같은 사용자가 보정과 평가에 함께 쓰이지 않도록 사용자 단위로 묶음을 나눈다.
    rng = np.random.default_rng(42)
    users = valid["visitorid"].unique()
    fold_of_user = dict(zip(users, rng.permutation(len(users)) % FOLDS))
    fold = valid["visitorid"].map(fold_of_user).to_numpy()

    out_of_fold = {}
    for method in METHODS:
        p = np.empty(len(valid))
        for k in range(FOLDS):
            test_mask = fold == k
            calibration = fit_calibration(
                method, raw[~test_mask], y[~test_mask], weight[~test_mask]
            )
            p[test_mask] = apply_calibration(raw[test_mask], calibration)
        out_of_fold[method] = p
        loss = log_loss(y, np.clip(p, 1e-7, 1 - 1e-7), sample_weight=weight)
        print(f"{method}: 교차 보정 시점 가중 Log loss {loss:.5f}", flush=True)

    method = min(
        CANDIDATES,
        key=lambda m: log_loss(
            y, np.clip(out_of_fold[m], 1e-7, 1 - 1e-7), sample_weight=weight
        ),
    )
    p = out_of_fold[method]
    threshold = best_f1_threshold(y, p, weight)
    calibration = fit_calibration(method, raw, y, weight)

    heavy = valid["heavy_user"].to_numpy() == 1
    report = {
        "model": SELECTED_MODEL,
        **calibration,
        "threshold": threshold,
        "cross_fit_log_loss": {
            m: float(log_loss(y, np.clip(out_of_fold[m], 1e-7, 1 - 1e-7), sample_weight=weight))
            for m in METHODS
        },
        "valid_raw": evaluate(valid, raw),
        "valid_cross_fit": evaluate(valid, p, threshold),
        "valid_reliability_point_weighted": reliability_table(y, p, weight),
        "valid_reliability_by_range": {
            m: reliability_by_edges(y, out_of_fold[m], weight, RELIABILITY_EDGES)
            for m in METHODS
        },
        "distinct_probabilities": {
            m: int(len(np.unique(out_of_fold[m].round(6)))) for m in METHODS
        },
        "valid_reliability_non_heavy_rows": reliability_table(
            y[~heavy], p[~heavy], np.ones((~heavy).sum())
        ),
    }
    (models_dir / "calibration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    main_metrics = report["valid_cross_fit"]["point_weighted"]
    print(f"선택한 보정: {method} / 임계값 {threshold:.4%}")
    print(
        f"valid(교차 보정) 시점 가중: 평균 예측 {main_metrics['mean_prediction']:.4%} / "
        f"실제 {main_metrics['positive_rate']:.4%} / Log loss {main_metrics['log_loss']:.5f} / "
        f"정밀도 {main_metrics['precision']:.2%} / 재현율 {main_metrics['recall']:.2%} / "
        f"F1 {main_metrics['f1']:.4f}"
    )
    print("확률 구간별 평균 예측 → 실제 구매 비율 (시점 가중, 교차 보정)")
    for m in METHODS:
        print(f"  {m} (서로 다른 확률 {report['distinct_probabilities'][m]:,}개)")
        for row in report["valid_reliability_by_range"][m]:
            low, high = row["range"]
            print(
                f"    {low:.1%}~{high:.1%}: 비중 {row['weight_share']:.2%} / "
                f"예측 {row['mean_prediction']:.3%} → 실제 {row['positive_rate']:.3%}"
            )


if __name__ == "__main__":
    main()
