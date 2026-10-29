"""일반 고객 기준으로 확률을 다시 보정해 새 모델 버전(v2)을 만든다. 배치 재학습의 첫 단계다.

v1은 valid 전체 고객으로 보정했는데, 행의 대부분을 조회 100회 이상인 소수 고객이 차지해
일반 고객에게는 확률이 높게 나온다 (docs/ml/extension-test-results.md). 서비스 고객은
모두 일반 고객 쪽이라 일반 고객 기준으로 다시 맞춘다.

- 모델(LightGBM)은 v1 그대로 쓰고 보정만 다시 맞춘다. 보정은 순서를 바꾸지 않는다.
- valid 일반 고객을 고객 단위로 A(보정)·B(평가) 반반으로 나눈다. test는 쓰지 않는다.
- 보정 방식은 v1과 같은 isotonic_smooth다. 가중치는 v1(조회 시점마다 합 1)과 달리 후보 상품
  하나하나를 같은 무게로 둔다. 대시보드는 후보 상품별 확률을 더해 예상 구매 수를 내므로
  상품 하나하나의 확률이 맞아야 합계가 맞는다.
- 임계값은 v1처럼 A 안에서 교차 보정으로 정한다.
- B에서 v1과 비교해 등록 기준(GATE)을 모두 통과해야 새 버전 폴더를 만든다.
  current.json은 바꾸지 않는다 (반영은 release.py use).

    python ml/product_purchase/recalibrate.py
"""
import json
import shutil
import time
from datetime import date

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

from calibrate_model import fit_calibration
from evaluate_extension_test import dashboard_coverage
from events import output_dir
from features import FEATURES
from modeling import apply_calibration, best_f1_threshold, load_split
from predict import PurchasePredictor
from release import MODELS_DIR, release_dir
from stage import STAGE_THRESHOLDS
from validate_stage import judge_all, points_from_frame, summarize

BASE_VERSION = "product_purchase_v1"
NEW_VERSION = "product_purchase_v2"
METHOD = "isotonic_smooth"
SEED = 42
FOLDS = 5
REPORT_PATH = output_dir / "recalibration_v2.json"

# B에서 v2가 통과해야 하는 기준. 보정은 순서를 바꾸지 않아 AUC·AP는 거의 같아야 한다.
RANKING_TOLERANCE = 0.002


def probability_metrics(y, p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return {
        "rows": int(len(y)),
        "mean_prediction": float(p.mean()),
        "positive_rate": float(y.mean()),
        "log_loss": float(log_loss(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "ap": float(average_precision_score(y, p)),
    }


def dashboard_gap(coverage):
    """대시보드 재생의 예상 합이 실제 합보다 몇 % 높은지 (음수면 낮음)."""
    groups = coverage["all_groups"]
    return groups["expected_sum"] / groups["actual_sum"] - 1


def gate(v1, v2):
    """등록 기준. 통과하지 못한 항목의 이유 목록을 돌려준다 (비어 있으면 통과)."""
    failures = []
    b1, b2 = v1["probability"], v2["probability"]
    if abs(b2["mean_prediction"] - b2["positive_rate"]) >= abs(b1["mean_prediction"] - b1["positive_rate"]):
        failures.append("평균 예측과 실제의 차이가 줄지 않음")
    if b2["log_loss"] >= b1["log_loss"]:
        failures.append("Log loss가 낮아지지 않음")
    if b2["brier"] >= b1["brier"]:
        failures.append("Brier가 낮아지지 않음")
    if abs(v2["dashboard_gap"]) >= abs(v1["dashboard_gap"]):
        failures.append("대시보드 예상 합과 실제 합의 차이가 줄지 않음")
    for name in ["roc_auc", "ap"]:
        if b2[name] < b1[name] - RANKING_TOLERANCE:
            failures.append(f"{name}가 v1보다 {RANKING_TOLERANCE} 넘게 낮아짐")
    return failures


def evaluate_version(frame, raw, calibration, predictor):
    """B 고객에서 한 버전의 확률 정확도, 대시보드 재생, 단계별 구매율을 계산한다."""
    p = apply_calibration(raw, calibration)
    y = frame["label"].to_numpy()
    points = points_from_frame(frame, p, predictor.base_probability)
    coverage = dashboard_coverage(points)
    return {
        "probability": probability_metrics(y, p),
        "base_probability": predictor.base_probability,
        "dashboard": coverage,
        "dashboard_gap": dashboard_gap(coverage),
        "stages": summarize(judge_all(points, STAGE_THRESHOLDS)),
    }


def write_version(calibration, threshold, report):
    directory = MODELS_DIR / NEW_VERSION
    base_dir = release_dir(BASE_VERSION)
    base_calibration = json.loads((base_dir / "calibration.json").read_text(encoding="utf-8"))
    directory.mkdir()
    shutil.copy(base_dir / f"{base_calibration['model']}.txt", directory)
    (directory / "calibration.json").write_text(
        json.dumps(
            {"model": base_calibration["model"], **calibration, "threshold": threshold},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    b = report["v2"]["probability"]
    metadata = {
        "version": NEW_VERSION,
        "created": date.today().isoformat(),
        "description": "v1 모델을 RetailRocket valid 일반 고객 기준으로 다시 보정",
        "based_on": BASE_VERSION,
        "training_data": f"{BASE_VERSION}와 같은 모델 파일 (다시 학습하지 않음)",
        "calibration_data": "RetailRocket valid 일반 고객(조회 100회 미만) 중 절반(A), 후보 상품별 같은 가중치",
        "evaluation": {
            "data": "RetailRocket valid 일반 고객 중 보정에 쓰지 않은 절반(B)",
            "mean_prediction": round(b["mean_prediction"], 6),
            "positive_rate": round(b["positive_rate"], 6),
            "log_loss": round(b["log_loss"], 6),
            "roc_auc": round(b["roc_auc"], 4),
            "dashboard_expected_vs_actual": round(report["v2"]["dashboard_gap"], 4),
            "threshold": round(threshold, 4),
        },
        "notes": "조회 100회 이상 고객에게는 확률이 낮게 나올 수 있다. docs/ml/recalibration-v2.md 참고",
    }
    (directory / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return directory


def main():
    if (MODELS_DIR / NEW_VERSION).exists():
        raise SystemExit(f"{NEW_VERSION}는 이미 있습니다. 버전 폴더는 덮어쓰지 않습니다.")
    started = time.time()

    print("valid 일반 고객을 읽고 v1 모델 점수를 계산합니다.", flush=True)
    frame = load_split("valid")
    heavy = frame["heavy_user"].to_numpy() == 1
    v1 = PurchasePredictor(release_dir(BASE_VERSION))
    raw_all = v1.model.predict(frame[FEATURES])
    y_all = frame["label"].to_numpy()

    frame = frame.loc[~heavy].reset_index(drop=True)
    raw = raw_all[~heavy]
    y = y_all[~heavy]

    # 고객 단위로 A(보정)·B(평가)를 나눈다
    rng = np.random.default_rng(SEED)
    users = frame["visitorid"].unique()
    half_of_user = dict(zip(users, rng.permutation(len(users)) % 2))
    in_a = frame["visitorid"].map(half_of_user).to_numpy() == 0
    print(f"A {in_a.sum():,}행 / B {(~in_a).sum():,}행", flush=True)

    ones = np.ones(len(frame))
    calibration = fit_calibration(METHOD, raw[in_a], y[in_a], ones[in_a])

    # 임계값: A를 고객 단위 묶음으로 나눠 보정에 안 쓴 묶음의 확률로 정한다
    a_frame = frame.loc[in_a]
    a_users = a_frame["visitorid"].unique()
    fold_of_user = dict(zip(a_users, rng.permutation(len(a_users)) % FOLDS))
    fold = a_frame["visitorid"].map(fold_of_user).to_numpy()
    raw_a, y_a = raw[in_a], y[in_a]
    out_of_fold = np.empty(len(raw_a))
    for k in range(FOLDS):
        held = fold == k
        fold_calibration = fit_calibration(METHOD, raw_a[~held], y_a[~held], np.ones((~held).sum()))
        out_of_fold[held] = apply_calibration(raw_a[held], fold_calibration)
    threshold = best_f1_threshold(y_a, out_of_fold, np.ones(len(y_a)))

    # B에서 v1과 v2 비교
    v2 = PurchasePredictor(release_dir(BASE_VERSION))
    v2.calibration = {"model": v1.calibration["model"], **calibration}
    v2.base_probability = v2.timeline([(0, "base")])[0]["probabilities"]["base"]
    b_frame = frame.loc[~in_a].reset_index(drop=True)
    print("B에서 v1과 v2를 비교합니다.", flush=True)
    report = {
        "split": {"a_rows": int(in_a.sum()), "b_rows": int((~in_a).sum()), "seed": SEED},
        "threshold": threshold,
        "v1": evaluate_version(b_frame, raw[~in_a], v1.calibration, v1),
        "v2": evaluate_version(b_frame, raw[~in_a], calibration, v2),
        # 조회 100회 이상 고객에게는 어떻게 되는지 기록만 한다 (서비스 고객이 아님)
        "heavy_users": {
            "v1": probability_metrics(y_all[heavy], apply_calibration(raw_all[heavy], v1.calibration)),
            "v2": probability_metrics(y_all[heavy], apply_calibration(raw_all[heavy], calibration)),
        },
    }
    failures = gate(report["v1"], report["v2"])
    report["gate"] = {"passed": not failures, "failures": failures}
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'B (일반 고객 평가용 절반)':<24}{'v1':>12}{'v2':>12}")
    for name, label in [
        ("mean_prediction", "평균 예측"),
        ("positive_rate", "실제 구매율"),
        ("log_loss", "Log loss"),
        ("brier", "Brier"),
        ("roc_auc", "ROC-AUC"),
        ("ap", "AP"),
    ]:
        a, b = report["v1"]["probability"][name], report["v2"]["probability"][name]
        fmt = "{:.3%}" if name in ("mean_prediction", "positive_rate") else "{:.5f}"
        print(f"  {label:<22}{fmt.format(a):>12}{fmt.format(b):>12}")
    for version in ["v1", "v2"]:
        d = report[version]["dashboard"]["all_groups"]
        print(
            f"  대시보드 재생 {version}: 예상 합 {d['expected_sum']:.1f} vs 실제 합 {d['actual_sum']} "
            f"({report[version]['dashboard_gap']:+.1%}), 적중률 {d['coverage']:.1%}"
        )
    print(f"  기준 확률(한 번 본 상품): v1 {v1.base_probability:.3%} / v2 {v2.base_probability:.3%}")
    print(f"  임계값: v1 {v1.threshold:.2%} / v2 {threshold:.2%}")
    print("\n단계별 대상 상품 구매율 (B)")
    for group in ["browsing", "comparing", "decided", "leaving"]:
        s1, s2 = report["v1"]["stages"][group], report["v2"]["stages"][group]
        t1 = f"{s1['target_purchase_rate']:.2%}" if s1["target_purchase_rate"] is not None else "-"
        t2 = f"{s2['target_purchase_rate']:.2%}" if s2["target_purchase_rate"] is not None else "-"
        print(
            f"  {group:<10} 비중 v1 {s1['share']:.1%} / v2 {s2['share']:.1%}  "
            f"아무거나 v1 {s1['any_purchase_rate']:.2%} / v2 {s2['any_purchase_rate']:.2%}  대상 v1 {t1} / v2 {t2}"
        )
    h = report["heavy_users"]
    print(
        f"\n조회 100회 이상 고객: 평균 예측 v1 {h['v1']['mean_prediction']:.3%} / v2 {h['v2']['mean_prediction']:.3%}"
        f" / 실제 {h['v1']['positive_rate']:.3%}"
    )

    if failures:
        print("\n등록 기준 미통과. 새 버전을 만들지 않습니다.")
        for failure in failures:
            print(f"  - {failure}")
    else:
        directory = write_version(calibration, threshold, report)
        print(f"\n등록 기준 통과. 새 버전을 만들었습니다: {directory}")
        print("반영하려면: python ml/product_purchase/release.py use v2")
    print(f"결과 저장: {REPORT_PATH} ({time.time() - started:.0f}초)")


if __name__ == "__main__":
    main()
