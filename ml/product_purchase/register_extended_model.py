"""시간 분할 피처 실험에서 고른 모델을 서비스 모델 버전 폴더로 등록한다 (조회·장바구니 입력).

다시 학습하지 않는다. 시뮬레이션·게임이 test 기간(8~9월) 기록을 재생하므로, 그 기간을 학습에
쓰지 않은 실험 모델(5~6월 학습, 7월 보정)을 그대로 쓴다. 문서의 test 성능이 시연에서 보이는
성능과 같다.

버전 폴더에는 모델, 보정, train 기간 상품 통계(item_stats.parquet), metadata.json을 넣는다.
서비스 반영(current.json)은 하지 않는다. 조회만 쓰는 백엔드와 입력이 달라서다.

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/register_extended_model.py            # view_cart_item → 다음 버전
"""
import argparse
import json
import shutil
from datetime import date

import numpy as np
import pandas as pd

import item_stats
from events import DEFAULT_OUTPUT_NAME, load_events, output_dir
from features_extended import EXPERIMENTS, experiment_features
from modeling import experiments_dir
from predict_extended import ITEM_STATS_FILE
from release import MODELS_DIR, next_version, normalize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="view_cart_item", choices=list(EXPERIMENTS))
    parser.add_argument("--version", help="기본값은 다음 버전 번호")
    args = parser.parse_args()
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit("시간 분할 실험 폴더에서 실행하세요 (PRODUCT_PURCHASE_DIR).")

    source = experiments_dir / args.experiment
    calibration = json.loads((source / "calibration.json").read_text(encoding="utf-8"))
    test = json.loads((source / "test_metrics.json").read_text(encoding="utf-8"))
    target = MODELS_DIR / normalize(args.version or next_version())
    if target.exists():
        raise SystemExit(f"이미 있는 버전입니다: {target}")

    print("train 기간 상품 통계를 계산합니다.", flush=True)
    events, _ = load_events()
    users = pd.read_parquet(output_dir / "users.parquet")
    table, defaults = item_stats.compute(events, users)
    # 서비스에서는 자기 묶음을 뺄 필요가 없으므로 train 기간 전체 통계만 담는다.
    full = table.xs(item_stats.OTHER, level="fold").reset_index()
    full["itemid"] = full["itemid"].astype(np.int64)

    target.mkdir(parents=True)
    shutil.copy(source / f"{calibration['model']}.txt", target)
    shutil.copy(source / "calibration.json", target)
    full.to_parquet(target / ITEM_STATS_FILE, index=False, compression="zstd")

    main_metrics = test["test"]["point_weighted"]
    top1 = test["pre_purchase_ranking"]["without_checkout_view"]["all_users"]
    metadata = {
        "version": target.name,
        "created": date.today().isoformat(),
        "description": "조회·장바구니·상품 통계 피처 모델 (판매자용). 시간 분할 실험의 "
        f"{args.experiment} 조합",
        "input": "view_cart",
        "features": experiment_features(args.experiment),
        "item_stats_defaults": {name: float(value) for name, value in defaults.items()},
        "training_data": "RetailRocket 2015-05-03 ~ 06-30 (기록이 이 기간 안에만 있는 사용자)",
        "calibration_data": "RetailRocket 2015-07-01 ~ 07-31 (기록이 이 기간 안에만 있는 사용자)",
        "item_stats_data": "RetailRocket 2015-05-03 ~ 06-30 전체 기록",
        "evaluation": {
            "data": "RetailRocket 2015-08-01 ~ 09-18 (기록이 이 기간 안에만 있는 사용자)",
            "ap": round(main_metrics["ap"], 4),
            "positive_rate": round(main_metrics["positive_rate"], 4),
            "roc_auc": round(main_metrics["roc_auc"], 4),
            "precision": round(main_metrics["precision"], 4),
            "recall": round(main_metrics["recall"], 4),
            "pre_purchase_top1": round(top1["model"], 4),
            "threshold": round(calibration["threshold"], 4),
        },
        "notes": "test 기간(8~9월) 기록을 학습·보정에 쓰지 않았다. 시뮬레이션은 그 기간을 재생한다. "
        "docs/ml/time-split-results.md 참고",
    }
    (target / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    size_mb = (target / ITEM_STATS_FILE).stat().st_size / 1e6
    print(f"등록: {target} (상품 통계 {len(full):,}개, {size_mb:.1f}MB)")
    print("current.json은 바꾸지 않았습니다.")


if __name__ == "__main__":
    main()
