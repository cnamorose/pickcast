import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from scipy.special import expit
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)


ml_dir = Path(__file__).resolve().parents[2]
model_dir = ml_dir / "data" / "artifacts" / "product_purchase_recent_day"
test_path = (
    ml_dir / "data" / "processed" / "product_purchase_v2"
    / "splits" / "test.csv"
)

settings = json.loads(
    (model_dir / "calibration.json").read_text(encoding="utf-8")
)
model = lgb.Booster(model_file=str(model_dir / "model.txt"))
features = settings["features"]
if model.feature_name() != features:
    raise ValueError("모델과 확률 보정에 사용한 피처가 다릅니다.")

columns = ["visitorid", "cutoff_timestamp", "label"] + features
dtypes = {name: "float32" for name in features}
dtypes.update({
    "visitorid": "int64",
    "cutoff_timestamp": "int64",
    "label": "int8",
})
data = pd.read_csv(test_path, usecols=columns, dtype=dtypes)
labels = data["label"].to_numpy()

raw_scores = model.predict(data[features], raw_score=True)
probabilities = expit(
    settings["coefficient"] * raw_scores + settings["intercept"]
)
threshold = settings["decision_threshold"]
predicted = probabilities >= threshold

true_positive = int(((predicted == 1) & (labels == 1)).sum())
false_positive = int(((predicted == 1) & (labels == 0)).sum())
false_negative = int(((predicted == 0) & (labels == 1)).sum())

metrics = {
    "rows": len(labels),
    "positive_rows": int(labels.sum()),
    "actual_purchase_rate": float(labels.mean()),
    "mean_predicted_probability": float(probabilities.mean()),
    "baseline_ap": float(labels.mean()),
    "model_ap": float(average_precision_score(labels, probabilities)),
    "roc_auc": float(roc_auc_score(labels, probabilities)),
    "log_loss": float(log_loss(labels, probabilities)),
    "brier_score": float(brier_score_loss(labels, probabilities)),
    "decision_threshold": float(threshold),
    "predicted_purchase_rows": int(predicted.sum()),
    "true_positive": true_positive,
    "false_positive": false_positive,
    "false_negative": false_negative,
    "precision": float(precision_score(labels, predicted, zero_division=0)),
    "recall": float(recall_score(labels, predicted, zero_division=0)),
    "f1": float(f1_score(labels, predicted, zero_division=0)),
}

# 구매한 후보가 있는 시점에서 상품 1순위 성능도 평가합니다.
data["probability"] = probabilities
multi_candidate = 0
evaluated = 0
tied_top = 0
random_success = 0.0
model_success = 0.0

for _, group in data.groupby(["visitorid", "cutoff_timestamp"], sort=False):
    if len(group) < 2:
        continue
    multi_candidate += 1

    positive_count = int(group["label"].sum())
    if positive_count == 0:
        continue

    evaluated += 1
    random_success += positive_count / len(group)

    top = group.loc[group["probability"].eq(group["probability"].max())]
    tied_top += int(len(top) > 1)
    model_success += top["label"].mean()

ranking = {
    "multi_candidate_snapshots": multi_candidate,
    "evaluated_purchase_snapshots": evaluated,
    "tied_top_snapshots": tied_top,
    "random_top1": float(random_success / evaluated) if evaluated else None,
    "model_top1": float(model_success / evaluated) if evaluated else None,
}

output_path = model_dir / "test_metrics.json"
output_path.write_text(
    json.dumps(
        {"metrics": metrics, "ranking": ranking},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

print("=== 상품별 구매 예측: 최종 평가 ===")
print(f"상품 행: {metrics['rows']:,}")
print(f"구매 정답: {metrics['positive_rows']:,}")
print(f"실제 구매 비율: {metrics['actual_purchase_rate']:.4%}")
print(f"평균 예측 확률: {metrics['mean_predicted_probability']:.4%}")
print(f"단순 기준 AP: {metrics['baseline_ap']:.6f}")
print(f"모델 AP: {metrics['model_ap']:.6f}")
print(f"ROC-AUC: {metrics['roc_auc']:.6f}")
print(f"Log loss: {metrics['log_loss']:.6f}")
print(f"Brier score: {metrics['brier_score']:.6f}")

print("\n=== 구매/비구매 판정 ===")
print(f"기준: {threshold:.4%}")
print(f"구매로 예측: {metrics['predicted_purchase_rows']:,}행")
print(f"정밀도: {metrics['precision']:.2%}")
print(f"재현율: {metrics['recall']:.2%}")
print(f"F1: {metrics['f1']:.4f}")

print("\n=== 구매 상품 1순위 ===")
print(f"평가한 예측 시점: {evaluated:,}")
if evaluated:
    print(f"무작위 선택: {ranking['random_top1']:.2%}")
    print(f"모델 1순위: {ranking['model_top1']:.2%}")
print(f"최고 점수 동점: {tied_top:,}")
print(f"\n저장 위치: {output_path}")
