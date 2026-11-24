"""시간 분할 실험의 test(2015-08-01 ~ 09-18)를 한 번 평가한다.

모델·보정·임계값은 train(5~6월)과 valid(7월)로 정했다. test 결과를 보고 다시 조정하지 않는다.
결과 파일이 이미 있으면 실행하지 않는다.

1. 기존 test 평가와 같은 지표: 시점 가중 AP·AUC·정밀도·재현율, 확률 구간별 예측 vs 실제,
   월별 예측 vs 실제, 조회 시점별 1순위 정답률, 사용자·상품 단위 AP
2. 단순 규칙 비교: 조회 시점별 1순위 정답률을 모델, 가장 많이 본 상품, 가장 최근에 본 상품,
   무작위로 비교 (전체 / 조회 100회 미만 고객)
3. 구매 직전 1순위 정답률: 구매한 사용자마다 첫 구매 직전 예측 시점 하나만 본다.
   - last_point: 첫 구매 직전 마지막 예측 시점
   - without_checkout_view: 그 시점에 방금 본 상품이 산 상품이면 한 시점 앞 (결제하러 들어간
     조회를 빼는 결과 화면·게임과 같은 규칙)

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/evaluate_time_split.py
"""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from calibrate_model import RELIABILITY_EDGES
from evaluate_extension_test import rule_ranking
from evaluate_test import by_month, candidate_ranking, pair_level
from events import DEFAULT_OUTPUT_NAME, load_events, output_dir
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


def pre_purchase_points(test, first_purchase):
    """구매한 사용자마다 첫 구매 직전 예측 시점 하나를 고른 행 마스크 두 가지."""
    keys = test[["visitorid", "cutoff_timestamp"]]
    before = keys["cutoff_timestamp"].to_numpy() < (
        keys["visitorid"].map(first_purchase).fillna(-1).to_numpy()
    )
    points = keys[before].drop_duplicates().sort_values(["visitorid", "cutoff_timestamp"])
    last = points.groupby("visitorid").tail(1)
    previous = points.groupby("visitorid").nth(-2)

    # 마지막 시점에 방금 본 상품(is_last_viewed)이 이후 산 상품이면 결제하러 들어간 조회로 본다.
    at_last = test.merge(last, on=["visitorid", "cutoff_timestamp"])
    checkout_users = at_last.loc[
        (at_last["is_last_viewed"] == 1) & (at_last["label"] == 1), "visitorid"
    ].unique()
    without_checkout = pd.concat(
        [
            last[~last["visitorid"].isin(checkout_users)],
            previous[previous["visitorid"].isin(checkout_users)],
        ]
    )

    def mask(selected):
        index = selected.set_index(["visitorid", "cutoff_timestamp"]).index
        return keys.set_index(["visitorid", "cutoff_timestamp"]).index.isin(index)

    return {
        "last_point": mask(last),
        "without_checkout_view": mask(without_checkout),
        "checkout_view_users": int(len(checkout_users)),
    }


def main():
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit("시간 분할 실험 폴더에서 실행하세요 (PRODUCT_PURCHASE_DIR).")
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
    non_heavy = (test["heavy_user"] == 0).to_numpy()

    print("첫 구매 시각을 읽습니다.", flush=True)
    events, _ = load_events()
    first_purchase = (
        events.loc[events["event"] == "transaction"].groupby("visitorid")["timestamp"].min()
    )
    del events
    pre = pre_purchase_points(test, first_purchase)

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
        "rule_ranking": {
            "all_users": rule_ranking(test, p),
            "non_heavy_users": rule_ranking(test[non_heavy], p[non_heavy]),
        },
        "pre_purchase_ranking": {
            "checkout_view_users": pre["checkout_view_users"],
            **{
                name: {
                    "all_users": rule_ranking(test[pre[name]], p[pre[name]]),
                    "non_heavy_users": rule_ranking(
                        test[pre[name] & non_heavy], p[pre[name] & non_heavy]
                    ),
                }
                for name in ("last_point", "without_checkout_view")
            },
        },
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    main_metrics = report["test"]["point_weighted"]
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
    for name, result in [
        ("과다 조회 제외", report["test"]["non_heavy_rows"]),
        ("반복 조회 시점", report["test"]["repeat_view_point_weighted"]),
    ]:
        print(f"{name}: AP {result['ap']:.4f} (기준 {result['positive_rate']:.4f}) / AUC {result['roc_auc']:.4f}")

    def print_ranking(title, ranking):
        print(title)
        for group, r in ranking.items():
            print(
                f"  {group}: 시점 {r['points']:,} / 모델 {r['model']:.2%} / 많이 본 상품 "
                f"{r['most_viewed']:.2%} / 최근 본 상품 {r['last_viewed']:.2%} / 무작위 {r['random']:.2%}"
            )

    print_ranking("조회 시점별 1순위 정답률", report["rule_ranking"])
    print_ranking("구매 직전 1순위 정답률", report["pre_purchase_ranking"]["last_point"])
    print_ranking(
        "구매 직전 1순위 정답률 (결제하러 들어간 조회 제외)",
        report["pre_purchase_ranking"]["without_checkout_view"],
    )
    print("확률 구간별 예측 → 실제 (시점 가중)")
    for row in report["reliability_by_range"]:
        low, high = row["range"]
        print(
            f"  {low:.1%}~{high:.1%}: 비중 {row['weight_share']:.2%} / "
            f"예측 {row['mean_prediction']:.3%} → 실제 {row['positive_rate']:.3%}"
        )
    print("월별 예측 → 실제 (시점 가중)")
    for month, row in report["by_month"].items():
        print(f"  {month}: 예측 {row['mean_prediction']:.3%} → 실제 {row['positive_rate']:.3%}")


if __name__ == "__main__":
    main()
