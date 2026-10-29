"""확장 기능(사용자 맞춤 화면, 판매자 대시보드)을 test로 한 번 확인한다.

기준값은 valid에서 정했다(docs/ml/stage-validation.md). test 결과를 보고 기준값이나 모델을
다시 조정하지 않는다. 결과 파일이 이미 있으면 실행하지 않는다.

1. 단계별 구매율: valid 검증과 같은 방법으로 test에서도 단계가 구매를 나누는지
2. 단순 규칙 비교: 후보 중 산 상품을 1위로 맞힌 비율을 모델, 가장 최근에 본 상품,
   가장 많이 본 상품, 무작위로 비교
3. 대시보드 90% 범위 적중률: test 기록을 시간순으로 재생해 매시 정각마다 "최근 30분 안에
   조회한 고객"으로 대시보드를 만들고, 상품별 90% 범위 안에 실제 구매 수가 들어오는 비율

조회 100회 이상 고객은 valid 검증과 같이 뺀다. 2번은 기존 test 평가(31.69%)와 같은
시점 집합에서 전체 고객 기준도 함께 계산한다.

    python ml/product_purchase/evaluate_extension_test.py
"""
import json
import time

import numpy as np
import pandas as pd

from dashboard import forecast_sales
from features import FEATURES
from modeling import apply_calibration, load_split, models_dir
from predict import PurchasePredictor
from stage import STAGE_THRESHOLDS
from validate_stage import judge_all, load_points, summarize, top1_baseline

REPORT_PATH = models_dir / "extension_test_metrics.json"

# 대시보드 재생: 매시 정각마다, 최근 30분 안에 조회한 고객을 "쇼핑 중"으로 본다 (서비스와 같은 기준)
ACTIVE_WINDOW_MS = 30 * 60_000
SNAPSHOT_EVERY_MS = 60 * 60_000
# 데이터 마지막 달은 이후 구매를 볼 기간이 짧아 실제 구매가 적게 잡히므로 뺀다
EXCLUDE_FROM = "2015-09"


def stage_rates():
    points = load_points("test")
    summary = summarize(judge_all(points, STAGE_THRESHOLDS))
    baseline = top1_baseline(points, STAGE_THRESHOLDS["min_views"])
    return summary, baseline, points


def rule_ranking(frame, p):
    """후보 2개 이상이고 산 후보가 있는 시점에서 각 방법의 1순위가 산 상품인 비율.

    가장 최근에 본 상품: 마지막 조회 후 경과 시간이 가장 짧은 후보
    가장 많이 본 상품: 조회 수가 가장 많은 후보 (같으면 더 최근에 본 상품)
    무작위: 후보 중 산 상품의 비율 (기대값)
    """
    data = frame[
        ["visitorid", "cutoff_timestamp", "candidate_count", "view_count",
         "seconds_since_last_view", "label"]
    ].copy()
    data["p"] = p
    data = data[data["candidate_count"] >= 2]
    keys = ["visitorid", "cutoff_timestamp"]
    data = data[data.groupby(keys)["label"].transform("max") == 1]

    def hit_rate(order_columns, ascending):
        top = data.sort_values(keys + order_columns, ascending=[True, True, *ascending])
        return float(top.groupby(keys, sort=False)["label"].first().mean())

    return {
        "points": int(data.groupby(keys).ngroups),
        "model": hit_rate(["p"], [False]),
        "last_viewed": hit_rate(["seconds_since_last_view"], [True]),
        "most_viewed": hit_rate(["view_count", "seconds_since_last_view"], [False, True]),
        "random": float(data.groupby(keys)["label"].mean().mean()),
    }


def dashboard_coverage(points):
    """매시 정각 대시보드를 재생해 상품별 90% 범위 적중률을 구한다."""
    starts = points["starts"][:-1]
    point_frame = pd.DataFrame(
        {
            "start": starts,
            "end": points["starts"][1:],
            "visitor": points["visitor"][starts],
            "cutoff": points["cutoff"][starts],
        }
    )
    # 조회 시각 t는 t 이후 첫 정각 T에서, T - 30분 < t 일 때 쇼핑 중이다
    snapshot = -(-point_frame["cutoff"] // SNAPSHOT_EVERY_MS) * SNAPSHOT_EVERY_MS
    point_frame["snapshot"] = snapshot
    point_frame = point_frame[snapshot - point_frame["cutoff"] < ACTIVE_WINDOW_MS]
    month = point_frame["snapshot"].astype("datetime64[ms]").dt.strftime("%Y-%m")
    point_frame = point_frame[month < EXCLUDE_FROM]
    # 정각마다 고객의 가장 최근 조회 시점 하나만 쓴다
    point_frame = point_frame.sort_values("cutoff").groupby(["snapshot", "visitor"]).tail(1)

    probabilities, bought = {}, {}
    for snap, lo, hi in zip(point_frame["snapshot"], point_frame["start"], point_frame["end"]):
        for item, p, label in zip(
            points["item"][lo:hi], points["probability"][lo:hi], points["label"][lo:hi]
        ):
            probabilities.setdefault((snap, item), []).append(float(p))
            bought[(snap, item)] = bought.get((snap, item), 0) + int(label)

    groups = []
    for key, values in probabilities.items():
        forecast = forecast_sales({key: values})[0]
        groups.append(
            {
                "expected": forecast["expected"],
                "low": forecast["low"],
                "high": forecast["high"],
                "actual": bought[key],
            }
        )

    def coverage(rows):
        if not rows:
            return None
        inside = [r["low"] <= r["actual"] <= r["high"] for r in rows]
        return {
            "groups": len(rows),
            "coverage": float(np.mean(inside)),
            "expected_sum": float(sum(r["expected"] for r in rows)),
            "actual_sum": int(sum(r["actual"] for r in rows)),
            "below_low": float(np.mean([r["actual"] < r["low"] for r in rows])),
            "above_high": float(np.mean([r["actual"] > r["high"] for r in rows])),
        }

    return {
        "snapshots": int(point_frame["snapshot"].nunique()),
        "customer_snapshots": int(len(point_frame)),
        "all_groups": coverage(groups),
        # 범위가 0~0이면 실제도 거의 0이라 적중률이 저절로 높아진다. 범위가 열린 경우만 따로 본다.
        "nonzero_range_groups": coverage([g for g in groups if g["high"] > 0]),
    }


def main():
    if REPORT_PATH.exists():
        raise SystemExit(f"test는 이미 평가했습니다: {REPORT_PATH}")
    started = time.time()

    print("1. 단계별 구매율", flush=True)
    summary, baseline, points = stage_rates()

    print("2. 단순 규칙 비교", flush=True)
    frame = load_split("test")
    predictor = PurchasePredictor()
    p = apply_calibration(predictor.model.predict(frame[FEATURES]), predictor.calibration)
    ranking = {
        "all_users": rule_ranking(frame, p),
        "non_heavy_users": rule_ranking(
            frame[frame["heavy_user"] == 0], p[(frame["heavy_user"] == 0).to_numpy()]
        ),
    }
    del frame

    print("3. 대시보드 90% 범위 적중률", flush=True)
    coverage = dashboard_coverage(points)

    report = {
        "thresholds": STAGE_THRESHOLDS,
        "stage_summary": summary,
        "top1_baseline": baseline,
        "rule_ranking": ranking,
        "dashboard_coverage": coverage,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n[1] 단계별 구매율 (조회 100회 이상 고객 제외)")
    for group in ["too_few_views", "browsing", "comparing", "decided", "leaving"]:
        s = summary[group]
        target = f"{s['target_purchase_rate']:.2%}" if s["target_purchase_rate"] is not None else "-"
        print(f"  {group:<14} 비중 {s['share']:>6.1%}  아무거나 {s['any_purchase_rate']:.2%}  대상 {target}")
    print(f"  기준선(모델 1위 상품) {baseline['top1_purchase_rate']:.2%}")

    print("\n[2] 1순위 정답률")
    for name, r in ranking.items():
        print(
            f"  {name}: 시점 {r['points']:,} / 모델 {r['model']:.2%} / 최근 본 상품 {r['last_viewed']:.2%}"
            f" / 많이 본 상품 {r['most_viewed']:.2%} / 무작위 {r['random']:.2%}"
        )

    print(f"\n[3] 대시보드 재생: 정각 {coverage['snapshots']:,}회, 쇼핑 중 고객 {coverage['customer_snapshots']:,}명")
    for name in ["all_groups", "nonzero_range_groups"]:
        c = coverage[name]
        if c:
            print(
                f"  {name}: 상품 {c['groups']:,}개 / 적중률 {c['coverage']:.1%} "
                f"(아래 {c['below_low']:.1%}, 위 {c['above_high']:.1%}) / "
                f"예상 합 {c['expected_sum']:.1f} vs 실제 합 {c['actual_sum']}"
            )
    print(f"\n결과 저장: {REPORT_PATH} ({time.time() - started:.0f}초)")


if __name__ == "__main__":
    main()
