"""10분 판매 비율을 valid 기간(7월)으로 만들어 버전 폴더에 넣는다 (horizon.py 참고).

valid를 10분 간격으로 재생해, 시각마다 쇼핑 중인 고객의 후보 상품을 (담았는지, 마지막 행동 뒤
지난 시간)으로 나누고, 다음 10분 안에 실제로 팔린 수 ÷ 모델 확률 합을 구한다. 모델의 확률 보정과
같은 valid 데이터이고, test(8~9월)는 evaluate_horizon.py로 확인한다.

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/fit_horizon_rates.py --version v3
"""
import argparse
import json

import numpy as np

from events import DEFAULT_OUTPUT_NAME, load_events, output_dir
from horizon import ACTIVE_MINUTES, HORIZON_MINUTES, RATES_FILE, RateCounter, within_horizon
from horizon_rows import MINUTE, period_bounds, predict_split, purchase_times, window_pairs
from release import release_dir

SPLIT = "valid"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--force", action="store_true", help="이미 있는 비율을 덮어쓴다")
    args = parser.parse_args()
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit("시간 분할 실험 폴더에서 실행하세요 (PRODUCT_PURCHASE_DIR).")
    directory = release_dir(args.version)
    target = directory / RATES_FILE
    if target.exists() and not args.force:
        raise SystemExit(f"이미 있습니다: {target} (--force로 덮어쓰기)")

    frame, p = predict_split(directory, SPLIT)
    events, _ = load_events()
    bought = purchase_times(frame, events)
    start, period_end = period_bounds(SPLIT, events, frame)
    step = HORIZON_MINUTES * MINUTE
    windows = int((period_end - step - start) // step) + 1
    carted = frame["cart_count"].to_numpy() > 0

    counter = RateCounter()
    for row, _, elapsed, sold in window_pairs(frame, bought, start, windows, step, ACTIVE_MINUTES):
        counter.add(p[row], elapsed, carted[row], sold)
    rates = counter.rates()
    report = {
        "data": "RetailRocket 2015-07-01 ~ 07-31 valid 사용자, 10분 간격 재생",
        "unit": "다음 10분 판매 수 ÷ 모델 확률 합 (경과 시간 구간별)",
        "groups": "그 시각에 그 상품을 장바구니에 담은 적이 있는지 (cart_count > 0)",
        "active_minutes": ACTIVE_MINUTES,
        **rates,
    }
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for name, flag in (("carted", True), ("not_carted", False)):
        q = within_horizon(np.array([0.1]), np.array([0.0]), flag, rates)[0]
        print(
            f"{name}: 판매 {rates[f'{name}_sales']:,}, 확률 합 {rates[f'{name}_sum_p']:,.0f}, "
            f"확률 10%인 상품의 직후 {HORIZON_MINUTES}분 확률 {q:.2%}"
        )
    print(f"저장: {target}")


if __name__ == "__main__":
    main()
