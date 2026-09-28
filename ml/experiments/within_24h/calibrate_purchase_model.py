import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    precision_recall_curve,
)


ml_dir = Path(__file__).resolve().parents[2]
model_dir = ml_dir / "data" / "artifacts" / "product_purchase_recent_day"
calibration_path = (
    ml_dir / "data" / "processed" / "product_purchase_v2"
    / "splits" / "calibration.csv"
)

model = lgb.Booster(model_file=str(model_dir / "model.txt"))
features = model.feature_name()

data = pd.read_csv(
    calibration_path,
    usecols=features + ["label"],
    dtype={**{name: "float32" for name in features}, "label": "int8"},
)
labels = data["label"].to_numpy()

raw_scores = model.predict(data[features], raw_score=True)
original = model.predict(data[features])

calibrator = LogisticRegression(max_iter=1000)
calibrator.fit(raw_scores.reshape(-1, 1), labels)
calibrated = calibrator.predict_proba(
    raw_scores.reshape(-1, 1)
)[:, 1]

precision, recall, thresholds = precision_recall_curve(
    labels, calibrated
)
f1 = (
    2 * precision[:-1] * recall[:-1]
    / (precision[:-1] + recall[:-1] + 1e-12)
)
best = int(np.argmax(f1))
threshold = float(thresholds[best])

report = {
    "method": "logistic calibration on LightGBM raw score",
    "features": features,
    "coefficient": float(calibrator.coef_[0, 0]),
    "intercept": float(calibrator.intercept_[0]),
    "decision_threshold": threshold,
    "threshold_method": "maximum F1 on calibration data",
    "calibration_rows": len(labels),
    "calibration_positives": int(labels.sum()),
    "actual_purchase_rate": float(labels.mean()),
    "original_mean": float(original.mean()),
    "calibrated_mean": float(calibrated.mean()),
    "calibrated_max": float(calibrated.max()),
    "original_log_loss": float(log_loss(labels, original)),
    "calibrated_log_loss": float(log_loss(labels, calibrated)),
    "original_brier_score": float(brier_score_loss(labels, original)),
    "calibrated_brier_score": float(brier_score_loss(labels, calibrated)),
    "threshold_precision": float(precision[best]),
    "threshold_recall": float(recall[best]),
    "threshold_f1": float(f1[best]),
}

output_path = model_dir / "calibration.json"
output_path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(f"보정 상품 행: {len(labels):,}")
print(f"실제 구매 비율: {labels.mean():.4%}")
print(f"보정 전 평균 예측: {original.mean():.4%}")
print(f"보정 후 평균 예측: {calibrated.mean():.4%}")
print(f"보정 후 최고 예측값: {calibrated.max():.4%}")
print(f"구매 판정 기준: {threshold:.4%}")
print(f"정밀도: {precision[best]:.2%}")
print(f"재현율: {recall[best]:.2%}")
print(f"F1: {f1[best]:.4f}")
print(f"저장 위치: {output_path}")
print("test 데이터는 사용하지 않았습니다.")
