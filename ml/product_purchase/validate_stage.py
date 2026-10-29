"""valid 데이터로 단계 판단(stage.py)이 실제 구매와 연결되는지 확인하고 기준값을 고른다.

RetailRocket에는 세션이 없어서 고객 한 명을 세션 하나로 본다 (서비스도 체험 한 번 = 세션 하나).
학습 행(조회 시점 × 후보 상품)에 서비스와 같은 모델·보정으로 확률을 붙이고, 고객별로 묶어
predictor.timeline()과 같은 형태로 다시 만든 뒤, 조회 시점마다 judge_stage를 돌린다.
각 시점에서 "그 뒤에 실제로 샀는지"(학습 행의 정답)를 단계별로 모은다.

- 아무 후보나 샀는가: 단계가 구매 의도를 잘 나누는지
- 단계가 가리킨 상품(items)을 샀는가: 비교 카드·강조할 상품을 제대로 골랐는지

조회 100회 이상 고객(heavy_user)은 뺀다. 소수 고객이 행 대부분을 차지하고(상위 100명이 84%),
조회 몇~수십 번인 체험 세션과 성격이 다르다. test는 쓰지 않는다 (기준값을 정한 뒤 한 번만 확인).

    python ml/product_purchase/validate_stage.py           # 지금 기준값으로 결과
    python ml/product_purchase/validate_stage.py --grid    # 주변 기준값과 비교
"""
import argparse
import itertools
import json
import time

import numpy as np

from events import output_dir
from features import FEATURES
from modeling import apply_calibration, load_split
from predict import PurchasePredictor
from stage import STAGE_THRESHOLDS, judge_stage

REPORT_PATH = output_dir / "stage_validation.json"
GRID_REPORT_PATH = output_dir / "stage_validation_grid.json"

# 한 상품을 몇 번 이상 봐야 단계 판단 대상으로 볼지 바꿔 본다 (지금은 2).
ITEM_VIEW_CHECK = [2, 3, 4]

# 결과 표에서 구경 중을 둘로 나눈다. 조회 3회 미만은 규칙상 판단하지 않는 구간이다.
GROUPS = ["too_few_views", "browsing", "comparing", "decided", "leaving"]

# --grid에서 바꿔 볼 기준값. 나머지는 STAGE_THRESHOLDS 그대로 둔다.
GRID = {
    "decided_lift": [1.5, 2.0, 2.5, 3.0],
    "decided_ratio": [1.5, 1.8, 2.0],
    "decided_share": [0.4, 0.5, 0.6],
    "comparing_lift": [1.5, 1.8, 2.0],
}


def load_points(split="valid", directory=None):
    """일반 고객 행에 확률을 붙이고, 조회 시점(고객, 시각) 경계를 구한다.

    test 평가(evaluate_extension_test.py)도 같은 방법을 쓰도록 구간을 받는다.
    directory를 주면 그 버전 폴더의 모델로, 없으면 지금 서비스 버전(current.json)으로 계산한다.
    """
    frame = load_split(split)
    frame = frame.loc[frame["heavy_user"] == 0].reset_index(drop=True)

    predictor = PurchasePredictor(directory) if directory else PurchasePredictor()
    raw = predictor.model.predict(frame[FEATURES])
    probability = apply_calibration(raw, predictor.calibration)
    return points_from_frame(frame, probability, predictor.base_probability)


def points_from_frame(frame, probability, base_probability):
    """학습 행(고객·시각 순으로 연속 저장)과 행별 확률로 조회 시점 단위 묶음을 만든다."""
    visitor = frame["visitorid"].to_numpy()
    cutoff = frame["cutoff_timestamp"].to_numpy()
    starts = np.flatnonzero(
        np.r_[True, (visitor[1:] != visitor[:-1]) | (cutoff[1:] != cutoff[:-1])]
    )
    return {
        "visitor": visitor,
        "cutoff": cutoff,
        "item": frame["itemid"].to_numpy(),
        "viewed_now": frame["seconds_since_last_view"].to_numpy() == 0,
        "label": frame["label"].to_numpy(),
        "probability": probability,
        "starts": np.r_[starts, len(frame)],
        "base_probability": base_probability,
    }


def judge_all(points, thresholds):
    """조회 시점마다 단계를 판단하고, 그 시점 이후 구매 여부를 함께 기록한다."""
    visitor, item, viewed_now = points["visitor"], points["item"], points["viewed_now"]
    label, probability, starts = points["label"], points["probability"], points["starts"]
    base = points["base_probability"]

    records = []
    timeline, current = [], None
    for k in range(len(starts) - 1):
        lo, hi = starts[k], starts[k + 1]
        if visitor[lo] != current:
            timeline, current = [], visitor[lo]
        items = item[lo:hi]
        timeline.append(
            {
                "viewed": items[viewed_now[lo:hi]].tolist(),
                "probabilities": dict(zip(items.tolist(), probability[lo:hi].tolist())),
            }
        )
        result = judge_stage(timeline, base, thresholds)
        bought = set(items[label[lo:hi] == 1].tolist())
        total_views = sum(len(snapshot["viewed"]) for snapshot in timeline)
        group = "too_few_views" if total_views < thresholds["min_views"] else result["stage"]
        records.append(
            (
                group,
                current,
                bool(bought),
                bool(bought & set(result["items"])) if result["items"] else None,
            )
        )
    return records


def top1_baseline(points, min_views):
    """조회 min_views회 이상 시점에서 모델 1위 상품을 실제로 산 비율.

    단계가 가리킨 상품이 "그냥 확률 1위 상품을 고르는 것"보다 나은지 비교하는 기준이다.
    """
    visitor, viewed_now, label = points["visitor"], points["viewed_now"], points["label"]
    probability, starts = points["probability"], points["starts"]
    hits, current, views = [], None, 0
    for k in range(len(starts) - 1):
        lo, hi = starts[k], starts[k + 1]
        if visitor[lo] != current:
            current, views = visitor[lo], 0
        views += int(viewed_now[lo:hi].sum())
        if views >= min_views:
            hits.append(label[lo:hi][np.argmax(probability[lo:hi])] == 1)
    return {"points": len(hits), "top1_purchase_rate": float(np.mean(hits))}


def summarize(records):
    total = len(records)
    summary = {}
    for group in GROUPS:
        rows = [r for r in records if r[0] == group]
        targeted = [r[3] for r in rows if r[3] is not None]
        summary[group] = {
            "points": len(rows),
            "share": len(rows) / total if total else 0.0,
            "users": len({r[1] for r in rows}),
            "any_purchase_rate": float(np.mean([r[2] for r in rows])) if rows else None,
            "target_purchase_rate": float(np.mean(targeted)) if targeted else None,
        }
    judged = [r for r in records if r[0] != "too_few_views"]
    summary["all_3plus_views"] = {
        "points": len(judged),
        "any_purchase_rate": float(np.mean([r[2] for r in judged])) if judged else None,
    }
    return summary


def print_summary(summary):
    print(f"{'단계':<14}{'시점':>9}{'비중':>8}{'고객':>9}{'아무거나 구매':>13}{'대상 상품 구매':>14}")
    for group in GROUPS:
        s = summary[group]
        any_rate = f"{s['any_purchase_rate']:.2%}" if s["any_purchase_rate"] is not None else "-"
        target = f"{s['target_purchase_rate']:.2%}" if s["target_purchase_rate"] is not None else "-"
        print(f"{group:<14}{s['points']:>9,}{s['share']:>8.1%}{s['users']:>9,}{any_rate:>13}{target:>14}")
    base = summary["all_3plus_views"]
    print(f"조회 3회 이상 전체: 시점 {base['points']:,} / 아무거나 구매 {base['any_purchase_rate']:.2%}")


def main():
    parser = argparse.ArgumentParser(description="valid로 단계 판단 검증")
    parser.add_argument("--grid", action="store_true", help="주변 기준값과 비교")
    args = parser.parse_args()

    started = time.time()
    print("valid를 읽고 확률을 계산합니다.", flush=True)
    points = load_points()
    print(f"조회 시점 {len(points['starts']) - 1:,}개 ({time.time() - started:.0f}초)", flush=True)

    current = summarize(judge_all(points, STAGE_THRESHOLDS))
    print("\n[지금 기준값]")
    print_summary(current)

    baseline = top1_baseline(points, STAGE_THRESHOLDS["min_views"])
    print(
        f"\n기준선: 조회 {STAGE_THRESHOLDS['min_views']}회 이상 시점에서 모델 1위 상품 구매율 "
        f"{baseline['top1_purchase_rate']:.2%} ({baseline['points']:,}시점)"
    )

    item_views = {}
    print("\n[판단 대상 상품의 최소 조회 수]")
    for views in ITEM_VIEW_CHECK:
        summary = summarize(judge_all(points, {**STAGE_THRESHOLDS, "min_item_views": views}))
        item_views[views] = summary
        print(
            f"  {views}회: "
            + " / ".join(
                f"{group} 비중 {summary[group]['share']:.1%} 대상 구매 "
                f"{summary[group]['target_purchase_rate'] or 0:.2%}"
                for group in ["comparing", "decided", "leaving"]
            )
        )

    report = {
        "thresholds": STAGE_THRESHOLDS,
        "summary": current,
        "top1_baseline": baseline,
        "min_item_views_check": item_views,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {REPORT_PATH} ({time.time() - started:.0f}초)")

    if args.grid:
        grid = []
        names = list(GRID)
        combos = list(itertools.product(*GRID.values()))
        print(f"\n기준값 {len(combos)}개 조합을 비교합니다.", flush=True)
        for n, values in enumerate(combos, 1):
            thresholds = {**STAGE_THRESHOLDS, **dict(zip(names, values))}
            summary = summarize(judge_all(points, thresholds))
            grid.append({"changed": dict(zip(names, values)), "summary": summary})
            print(f"  {n}/{len(combos)} 완료 ({time.time() - started:.0f}초)", flush=True)
        GRID_REPORT_PATH.write_text(json.dumps(grid, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"결과 저장: {GRID_REPORT_PATH} ({time.time() - started:.0f}초)")


if __name__ == "__main__":
    main()
