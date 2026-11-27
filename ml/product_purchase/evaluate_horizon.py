""""앞으로 10분 예상 판매량"이 실제와 맞는지 10분 간격으로 재생해 확인한다.

구간 시작부터 10분 간격의 시각 t마다, 그때 쇼핑 중인 고객(마지막 행동이 24시간 안)의 후보 상품별로
horizon.py의 10분 확률을 구하고, 실제로 (t, t+10분]에 산 것과 비교한다.

- 시각 t에 쓰는 확률은 t 이전 마지막 예측 시점의 확률이다 (학습 데이터 행과 같은 피처).
- t 전에 이미 산 상품은 뺀다. 같은 사용자·상품은 첫 구매만 센다.
- 아직 들어오지 않은 고객, 보거나 담지 않고 산 상품의 판매는 예측 대상이 아니다.
  이 몫은 "전체 판매 중 예측 대상 비율"로 따로 적는다.

valid는 10분 판매 비율을 만든 데이터라 맞는지만 확인하는 용도이고, test(8~9월)가 확인 결과다.

지표
- 전체 합계: 예상 판매 합 vs 실제 판매 합 (담은 상품·담지 않은 상품 따로)
- 확률 구간별 보정: 10분 확률을 구간으로 나눠 평균 예측과 실제 구매 비율
- 10분 구간별: 예상 판매 수와 실제 판매 수의 상관, 평균 절대 오차(직전 10분 실제 값을 그대로
  쓰는 단순 예측과 비교), 1시간 합의 상관
- 미리 볼 수 있는 판매: 아무 10분 구간의 판매 중 구간 시작 전에 이미 보거나 담은 상품의 비율

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/evaluate_horizon.py --version v3 --split valid
    python ml/product_purchase/evaluate_horizon.py --version v3 --split test
"""
import argparse
import json

import numpy as np
import pandas as pd

from events import DEFAULT_OUTPUT_NAME, first_purchase_times, load_events, output_dir
from horizon import ACTIVE_MINUTES, HORIZON_MINUTES, load_rates, within_horizon
from horizon_rows import MINUTE, period_bounds, predict_split, purchase_times, window_pairs
from release import release_dir

EDGES = [0, 0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0000001]
REPORT_DIR = output_dir / "horizon"


def accumulate(frame, p, bought, rates, start, windows):
    """10분 구간별 예상·실제 판매와 확률 구간별 보정 표를 모은다."""
    step = HORIZON_MINUTES * MINUTE
    carted = frame["cart_count"].to_numpy() > 0
    groups = ("all", "carted", "not_carted")
    expected = {name: np.zeros(windows) for name in groups}
    actual = {name: np.zeros(windows) for name in groups}
    bins = len(EDGES) - 1
    bin_q, bin_y, bin_n = np.zeros(bins), np.zeros(bins), np.zeros(bins)
    pairs = 0
    for row, k, elapsed, sold in window_pairs(frame, bought, start, windows, step, ACTIVE_MINUTES):
        q = within_horizon(p[row], elapsed, carted[row], rates)
        hit = sold.astype(float)
        for name, mask in (("all", slice(None)), ("carted", carted[row]), ("not_carted", ~carted[row])):
            expected[name] += np.bincount(k[mask], weights=q[mask], minlength=windows)
            actual[name] += np.bincount(k[mask], weights=hit[mask], minlength=windows)
        b = np.clip(np.searchsorted(EDGES, q, side="right") - 1, 0, bins - 1)
        bin_q += np.bincount(b, weights=q, minlength=bins)
        bin_y += np.bincount(b, weights=hit, minlength=bins)
        bin_n += np.bincount(b, minlength=bins)
        pairs += len(row)

    reliability = [
        {
            "bin": f"{EDGES[i]:.1%}~{min(EDGES[i + 1], 1):.1%}",
            "pairs": int(bin_n[i]),
            "mean_predicted": float(bin_q[i] / bin_n[i]),
            "actual_rate": float(bin_y[i] / bin_n[i]),
        }
        for i in range(bins) if bin_n[i] > 0
    ]
    return expected, actual, reliability, pairs


def all_purchases_per_window(events, users, start, windows):
    """구간 고객의 모든 첫 구매(사용자·상품별)를 10분 구간에 나눠 센다."""
    step = HORIZON_MINUTES * MINUTE
    first = first_purchase_times(events[events["visitorid"].isin(users)])
    k = (first.to_numpy() - 1 - start) // step  # (t, t+step]에 들어가는 k
    k = k[(k >= 0) & (k < windows)]
    return np.bincount(k, minlength=windows).astype(float)


def visible_share(events, users):
    """아무 10분 구간의 판매 중, 구간 시작 전에 이미 보거나 담은 상품의 비율(평균).

    구매마다 그 상품을 처음 보거나 담은 뒤 산 시간 L에 대해, 무작위 10분 구간에서 구간 시작이
    처음 행동 뒤일 확률은 min(1, L / 10분)이다. 보거나 담지 않고 산 구매는 0이다.
    """
    mine = events[events["visitorid"].isin(users)]
    touches = mine[mine["event"].isin(["view", "addtocart"])]
    first_touch = touches.groupby(["visitorid", "itemid"])["timestamp"].min()
    bought = first_purchase_times(mine)
    touch = first_touch.reindex(bought.index).to_numpy()
    lag = np.nan_to_num((bought.to_numpy() - touch) / MINUTE, nan=0.0).clip(0, None)
    return float(np.minimum(1, lag / HORIZON_MINUTES).mean()), int(len(bought))


def window_metrics(expected, actual):
    previous = np.r_[np.nan, actual[:-1]]
    valid = ~np.isnan(previous)
    hours = len(expected) // 6 * 6
    hourly_e = expected[:hours].reshape(-1, 6).sum(axis=1)
    hourly_a = actual[:hours].reshape(-1, 6).sum(axis=1)
    return {
        "windows": int(len(expected)),
        "mean_expected": float(expected.mean()),
        "mean_actual": float(actual.mean()),
        "correlation": float(np.corrcoef(expected, actual)[0, 1]),
        "mae": float(np.abs(expected - actual).mean()),
        "mae_previous_window": float(np.abs(previous[valid] - actual[valid]).mean()),
        "hourly_correlation": float(np.corrcoef(hourly_e, hourly_a)[0, 1]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--split", choices=["valid", "test"], required=True)
    args = parser.parse_args()
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit("시간 분할 실험 폴더에서 실행하세요 (PRODUCT_PURCHASE_DIR).")
    report_path = REPORT_DIR / f"{args.split}_metrics.json"
    if args.split == "test" and report_path.exists():
        raise SystemExit(f"이미 test까지 평가했습니다: {report_path}")

    directory = release_dir(args.version)
    rates = load_rates(directory)
    print(f"{args.split} 행의 확률을 계산합니다.", flush=True)
    frame, p = predict_split(directory, args.split)
    events, _ = load_events()
    bought = purchase_times(frame, events)
    start, period_end = period_bounds(args.split, events, frame)
    step = HORIZON_MINUTES * MINUTE
    windows = int((period_end - step - start) // step) + 1
    users = pd.unique(frame["visitorid"])

    print(f"10분 구간 {windows:,}개를 계산합니다.", flush=True)
    expected, actual, reliability, pairs = accumulate(frame, p, bought, rates, start, windows)
    total = all_purchases_per_window(events, users, start, windows)
    share, purchases = visible_share(events, users)

    report = {
        "version": directory.name,
        "split": args.split,
        "method": "10분 판매 비율 (fit_horizon_rates.py)",
        "horizon_minutes": HORIZON_MINUTES,
        "active_minutes": ACTIVE_MINUTES,
        "pairs": pairs,
        "totals": {
            name: {"expected": float(expected[name].sum()), "actual": float(actual[name].sum())}
            for name in expected
        },
        "all_purchases": float(total.sum()),
        "predictable_share": float(actual["all"].sum() / total.sum()),
        "visible_share": {"share": share, "purchases": purchases},
        "window": window_metrics(expected["all"], actual["all"]),
        "reliability": reliability,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"(시각, 후보) 쌍 {pairs:,}개")
    for name, t in report["totals"].items():
        print(f"  {name}: 예상 {t['expected']:,.1f} / 실제 {t['actual']:,.0f}")
    print(f"전체 판매 {total.sum():,.0f} 중 예측 대상 {report['predictable_share']:.1%}")
    print(f"미리 볼 수 있는 판매 {share:.1%} (구매 {purchases:,}건)")
    w = report["window"]
    print(
        f"10분 구간: 상관 {w['correlation']:.3f}, 평균 절대 오차 {w['mae']:.3f} "
        f"(직전 구간 값 {w['mae_previous_window']:.3f}), 1시간 합 상관 {w['hourly_correlation']:.3f}"
    )
    print("확률 구간별 보정")
    for r in reliability:
        print(f"  {r['bin']:>14}: {r['pairs']:>11,}쌍  예측 {r['mean_predicted']:.3%}  실제 {r['actual_rate']:.3%}")
    print(f"저장: {report_path}")


if __name__ == "__main__":
    main()
