"""확정한 모델·보정·임계값으로 test를 한 번 평가한다.

test 결과를 보고 모델이나 임계값을 다시 조정하지 않는다. 결과 파일이 이미 있으면
실행하지 않는다.
"""
import json

import lightgbm as lgb
import numpy as np
from sklearn.metrics import average_precision_score

from features import FEATURES
from modeling import (
    apply_calibration,
    evaluate,
    load_split,
    models_dir,
    point_weights,
    reliability_by_edges,
    reliability_table,
)
from calibrate_model import RELIABILITY_EDGES


def candidate_ranking(test, p):
    """후보가 2개 이상이고 구매한 후보가 있는 시점에서 1순위가 구매 상품인 비율."""
    frame = test[["visitorid", "cutoff_timestamp", "candidate_count", "label"]].copy()
    frame["p"] = p
    frame = frame[frame["candidate_count"] >= 2]
    keys = ["visitorid", "cutoff_timestamp"]
    grouped = frame.groupby(keys)
    has_positive = grouped["label"].transform("max") == 1
    frame = frame[has_positive]
    top = frame.loc[frame.groupby(keys)["p"].idxmax()]
    random_hit = frame.groupby(keys)["label"].mean()
    return {
        "points": int(len(top)),
        "top1_hit_rate": float(top["label"].mean()),
        "random_hit_rate": float(random_hit.mean()),
    }


def by_month(test, p, weight):
    """예측 월별 실제 구매 비율과 평균 예측. 데이터 끝에 가까울수록 관찰 기간이 짧다."""
    frame = test[["cutoff_timestamp", "label"]].copy()
    frame["month"] = (
        frame["cutoff_timestamp"].astype("datetime64[ms]").dt.strftime("%Y-%m")
    )
    frame["p"] = p
    frame["w"] = weight
    result = {}
    for month, group in frame.groupby("month"):
        w = group["w"].to_numpy()
        result[month] = {
            "rows": int(len(group)),
            "positive_rate": float(np.average(group["label"], weights=w)),
            "mean_prediction": float(np.average(group["p"], weights=w)),
        }
    return result


def pair_level(test, p):
    """사용자·상품 단위: 여러 시점에서 받은 확률 중 최댓값으로 구매 여부를 구분하는 정도."""
    frame = test[["visitorid", "itemid", "label"]].copy()
    frame["p"] = p
    pairs = frame.groupby(["visitorid", "itemid"]).agg(label=("label", "max"), p=("p", "max"))
    return {
        "pairs": int(len(pairs)),
        "positive_pairs": int(pairs["label"].sum()),
        "positive_rate": float(pairs["label"].mean()),
        "ap": float(average_precision_score(pairs["label"], pairs["p"])),
    }


def main():
    output_path = models_dir / "test_metrics.json"
    if output_path.exists():
        raise SystemExit(f"test는 이미 평가했습니다: {output_path}")

    calibration = json.loads((models_dir / "calibration.json").read_text(encoding="utf-8"))
    model = lgb.Booster(model_file=str(models_dir / f"{calibration['model']}.txt"))
    threshold = calibration["threshold"]

    print("test를 읽고 평가합니다.", flush=True)
    test = load_split("test")
    p = apply_calibration(model.predict(test[FEATURES]), calibration)
    y = test["label"].to_numpy()
    weight = point_weights(test)

    report = {
        "model": calibration["model"],
        "calibration": calibration["method"],
        "threshold": threshold,
        "test": evaluate(test, p, threshold),
        "reliability_by_range": reliability_by_edges(y, p, weight, RELIABILITY_EDGES),
        "reliability_deciles": reliability_table(y, p, weight),
        "candidate_ranking": candidate_ranking(test, p),
        "by_month": by_month(test, p, weight),
        "pair_level": pair_level(test, p),
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    main_metrics = report["test"]["point_weighted"]
    non_heavy = report["test"]["non_heavy_rows"]
    ranking = report["candidate_ranking"]
    print(
        f"시점 가중: AP {main_metrics['ap']:.4f} (기준 {main_metrics['positive_rate']:.4f}) / "
        f"AUC {main_metrics['roc_auc']:.4f} / Log loss {main_metrics['log_loss']:.5f} / "
        f"Brier {main_metrics['brier']:.5f}"
    )
    print(
        f"평균 예측 {main_metrics['mean_prediction']:.4%} / 실제 {main_metrics['positive_rate']:.4%}"
    )
    print(
        f"구매 판정(임계값 {threshold:.4%}): 정밀도 {main_metrics['precision']:.2%} / "
        f"재현율 {main_metrics['recall']:.2%} / F1 {main_metrics['f1']:.4f}"
    )
    print(f"과다 조회 제외: AP {non_heavy['ap']:.4f} / AUC {non_heavy['roc_auc']:.4f}")
    print(
        f"후보 순위: {ranking['points']:,}개 시점 1순위 정답률 {ranking['top1_hit_rate']:.2%} "
        f"(무작위 {ranking['random_hit_rate']:.2%})"
    )
    print("확률 구간별 예측 → 실제 (시점 가중)")
    for row in report["reliability_by_range"]:
        low, high = row["range"]
        print(
            f"  {low:.1%}~{high:.1%}: 비중 {row['weight_share']:.2%} / "
            f"예측 {row['mean_prediction']:.3%} → 실제 {row['positive_rate']:.3%}"
        )


if __name__ == "__main__":
    main()
