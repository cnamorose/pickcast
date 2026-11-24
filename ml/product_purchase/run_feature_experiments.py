"""피처 묶음을 더하고 빼며 LightGBM을 학습하고 valid(7월)로 비교한다.

모델 설정은 train_models.py와 같고, 시간 분할 기준선에서 고른 point 가중치 하나만 쓴다.
모든 실험이 같은 행(build_extended_rows.py의 조회·담기 시점)에서 학습·평가되므로,
차이는 피처 묶음에서만 생긴다. test는 사용하지 않는다.

실험마다 feature_experiments/<이름>/에 모델(lgbm_point.txt)을 저장하고,
비교 결과는 feature_experiments/valid_metrics.json에 모은다.

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/run_feature_experiments.py
    python ml/product_purchase/run_feature_experiments.py --only view view_cart
"""
import argparse
import json
from time import perf_counter

import lightgbm as lgb

from evaluate_time_split import first_purchase_by_user, pre_purchase_ranking
from events import DEFAULT_OUTPUT_NAME, output_dir
from features_extended import ALL_FEATURES, EXPERIMENTS, experiment_features
from modeling import (
    evaluate,
    experiments_dir,
    extended_rows_dir,
    load_split,
    point_weights,
    row_weights,
)
from train_models import EARLY_STOPPING, MAX_ROUNDS, PARAMS


MODEL_NAME = "lgbm_point"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+", choices=list(EXPERIMENTS))
    args = parser.parse_args()
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit("시간 분할 실험 폴더에서 실행하세요 (PRODUCT_PURCHASE_DIR).")

    experiments_dir.mkdir(parents=True, exist_ok=True)
    report_path = experiments_dir / "valid_metrics.json"
    report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.exists()
        else {"experiments": {}}
    )

    print("train/valid를 읽습니다.", flush=True)
    train = load_split("train", ALL_FEATURES, extended_rows_dir)
    valid = load_split("valid", ALL_FEATURES, extended_rows_dir, ["touched_now"])
    print(f"train {len(train):,}행 / valid {len(valid):,}행", flush=True)
    train_weight = row_weights(train, "point")
    valid_weight = point_weights(valid)
    first_purchase = first_purchase_by_user()

    for name in args.only or EXPERIMENTS:
        features = experiment_features(name)
        started = perf_counter()
        model = lgb.train(
            PARAMS,
            lgb.Dataset(train[features], train["label"], weight=train_weight),
            num_boost_round=MAX_ROUNDS,
            valid_sets=[lgb.Dataset(valid[features], valid["label"], weight=valid_weight)],
            valid_names=["valid"],
            callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)],
        )
        target = experiments_dir / name
        target.mkdir(exist_ok=True)
        model.save_model(target / f"{MODEL_NAME}.txt", num_iteration=model.best_iteration)

        # 순위 지표는 보정과 무관하므로 보정 전 점수로 비교한다.
        p = model.predict(valid[features], num_iteration=model.best_iteration)
        importance = model.feature_importance("gain")
        result = evaluate(valid, p)
        ranking = pre_purchase_ranking(valid, p, first_purchase, "touched_now")
        report["experiments"][name] = {
            "groups": EXPERIMENTS[name],
            "features": features,
            "best_iteration": model.best_iteration,
            "train_seconds": round(perf_counter() - started, 1),
            "feature_importance_gain": dict(
                zip(features, (importance / importance.sum()).round(4).tolist())
            ),
            "valid": result,
            "pre_purchase_ranking": ranking,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        main_metrics = result["point_weighted"]
        top1 = ranking["without_checkout_view"]["all_users"]
        print(
            f"{name:<20} 반복 {model.best_iteration:>4} | 시점 가중 AP {main_metrics['ap']:.4f} / "
            f"AUC {main_metrics['roc_auc']:.4f} | 일반 고객 AP {result['non_heavy_rows']['ap']:.4f} | "
            f"구매 직전(결제 조회 제외) 1순위 {top1['model']:.2%} "
            f"(많이 본 상품 {top1['most_viewed']:.2%}, {top1['points']:,}명)",
            flush=True,
        )


if __name__ == "__main__":
    main()
