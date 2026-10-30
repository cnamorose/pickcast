"""배치 재학습 파이프라인. 체험 데이터가 쌓이면 보정을 다시 맞추고, 기준을 통과하면 새 버전으로 등록한다.

    python ml/product_purchase/pipeline.py <백엔드가 내보낸 기록 파일>
    python ml/product_purchase/pipeline.py <기록 파일> --dry-run     # 스위치와 상관없이 평가까지만
    python ml/product_purchase/pipeline.py --build-reference          # 참조 파일 만들기 (처음 한 번)

단계 (어디서 멈췄는지와 숫자를 리포트로 남긴다):
  ① 스위치 확인     ml/pipeline_config.json의 retrain_enabled가 false면 멈춘다
  ② 학습 데이터     기록 파일 → 정제 → 학습 행 (experience.py)
  ③ 양 확인         학습에 쓸 수 있는 체험 세션이 min_sessions 미만이면 멈춘다
  ④ 재보정         지금 서비스 모델의 점수에 보정을 다시 맞춘다. 모델(LightGBM)은 그대로다.
                   체험 데이터만으로는 적어 흔들리므로 RetailRocket 일반 고객 A 절반과 합치고,
                   체험 행에는 EXPERIENCE_WEIGHT만큼 가중치를 준다.
  ⑤ 평가           체험 평가용(eval)에서 지금 버전보다 확률이 정확해야 하고,
                   RetailRocket 일반 고객 B 절반에서 지금 버전보다 크게 나빠지면 안 된다.
                   단계 판단의 대표 흐름(stage.STAGE_SCENARIOS)도 의도한 단계로 나와야 한다.
  ⑥ 등록           통과하면 다음 번호의 버전 폴더를 만든다
  ⑦ 반영           auto_release가 true면 current.json을 바꾼다. false면 명령만 안내한다.

--dry-run은 ①과 ⑥⑦을 건너뛰고 ②~⑤까지만 돌린다. 배포 전에 흐름을 확인할 때 쓴다.

RetailRocket 원본 학습 데이터(500MB 이상)는 배포 서버에 없으므로, 보정·비교에 쓰는
valid 일반 고객 행만 뽑은 참조 파일(REFERENCE_PATH)을 한 번 만들어 둔다. 고객을 A·B로 나누는
방법은 v2를 만든 recalibrate.py와 같다.
"""
import argparse
import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from calibrate_model import fit_calibration
from events import output_dir
from experience import EXPERIENCE_DIR, build_dataset
from features import FEATURES
from modeling import apply_calibration, best_f1_threshold, load_split
from pipeline_config import load_pipeline_config
from predict import PurchasePredictor
from recalibrate import METHOD, SEED, probability_metrics
from release import MODELS_DIR, current_version, next_version, register_version, release_dir, use_version
from stage import scenario_mismatches

REFERENCE_PATH = output_dir / "pipeline_reference.parquet"

# 체험 행 하나를 RetailRocket 행 몇 개만큼 반영할지. 체험 데이터가 쌓일수록 영향이 커진다.
EXPERIENCE_WEIGHT = 10.0
# RetailRocket B에서 Log loss가 지금 버전보다 이 비율 넘게 나빠지면 등록하지 않는다
PUBLIC_LOG_LOSS_TOLERANCE = 0.01


def build_reference(path=REFERENCE_PATH):
    """RetailRocket valid 일반 고객 행과 A·B 구분을 참조 파일로 저장한다 (원본 데이터가 있는 곳에서 한 번)."""
    frame = load_split("valid")
    frame = frame.loc[frame["heavy_user"] == 0].reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    users = frame["visitorid"].unique()
    half_of_user = dict(zip(users, rng.permutation(len(users)) % 2))
    frame["half"] = np.where(frame["visitorid"].map(half_of_user) == 0, "A", "B")
    frame[["visitorid", "cutoff_timestamp", "itemid", *FEATURES, "label", "half"]].to_parquet(path, index=False)
    return path, len(frame)


def gate(current, candidate):
    """등록 기준. 통과하지 못한 이유 목록을 돌려준다 (비어 있으면 통과)."""
    failures = []
    exp_now, exp_new = current["experience_eval"], candidate["experience_eval"]
    if exp_new["rows"] == 0 or exp_new["positive_rate"] == 0:
        failures.append("체험 평가용 데이터에 구매가 없어 비교할 수 없음")
    else:
        if exp_new["log_loss"] >= exp_now["log_loss"]:
            failures.append("체험 평가용 Log loss가 낮아지지 않음")
        if abs(exp_new["mean_prediction"] - exp_new["positive_rate"]) > abs(
            exp_now["mean_prediction"] - exp_now["positive_rate"]
        ):
            failures.append("체험 평가용 평균 예측과 실제의 차이가 커짐")
    pub_now, pub_new = current["public_b"], candidate["public_b"]
    if pub_new["log_loss"] > pub_now["log_loss"] * (1 + PUBLIC_LOG_LOSS_TOLERANCE):
        failures.append(
            f"공개 데이터(RetailRocket B) Log loss가 {PUBLIC_LOG_LOSS_TOLERANCE:.0%} 넘게 나빠짐"
        )
    return failures


def _metrics_or_empty(y, p):
    if len(y) == 0:
        return {"rows": 0, "positive_rate": 0.0}
    if y.min() == y.max():
        # 정답이 한 종류뿐이면 AUC·AP를 계산할 수 없어 확률 지표만 남긴다
        return {
            "rows": int(len(y)),
            "mean_prediction": float(p.mean()),
            "positive_rate": float(y.mean()),
            "log_loss": float(-np.mean(y * np.log(np.clip(p, 1e-7, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-7, 1)))),
        }
    return probability_metrics(y, p)


def run(
    export_path,
    dry_run=False,
    config=None,
    models_dir=MODELS_DIR,
    experience_root=EXPERIENCE_DIR,
    reference_path=REFERENCE_PATH,
):
    """파이프라인을 실행하고 리포트(dict)를 돌려준다. 멈춘 단계는 report["stopped"]에 남는다."""
    config = config or load_pipeline_config()
    report = {"started": datetime.now().isoformat(timespec="seconds"), "dry_run": dry_run, "config": config}

    # ① 스위치
    if not dry_run and not config["retrain_enabled"]:
        report["stopped"] = "retrain_disabled"
        return report

    # ② 학습 데이터
    dataset_version = datetime.now().strftime("%Y%m%d-%H%M%S")
    dataset_dir, dataset = build_dataset(export_path, experience_root, version=dataset_version)
    report["dataset"] = {"version": dataset_version, "path": str(dataset_dir), **dataset}
    rows = pd.read_parquet(dataset_dir / "training_rows.parquet")

    # ③ 양
    usable = int(rows.loc[rows["split"] == "train", "session_id"].nunique())
    report["usable_train_sessions"] = usable
    if usable < config["min_sessions"]:
        report["stopped"] = "not_enough_sessions"
        _save(report, dataset_dir)
        return report

    # ④ 재보정: 지금 서비스 버전의 모델 점수에 보정을 다시 맞춘다
    base_version = current_version(models_dir)
    current = PurchasePredictor(release_dir(base_version, models_dir))
    reference = pd.read_parquet(reference_path)
    ref_raw = current.model.predict(reference[FEATURES])
    ref_y = reference["label"].to_numpy()
    in_a = reference["half"].to_numpy() == "A"
    exp_raw = current.model.predict(rows[FEATURES]) if len(rows) else np.empty(0)
    exp_y = rows["label"].to_numpy()
    exp_train = rows["split"].to_numpy() == "train"

    fit_raw = np.r_[ref_raw[in_a], exp_raw[exp_train]]
    fit_y = np.r_[ref_y[in_a], exp_y[exp_train]]
    fit_w = np.r_[np.ones(in_a.sum()), np.full(exp_train.sum(), EXPERIENCE_WEIGHT)]
    calibration = fit_calibration(METHOD, fit_raw, fit_y, fit_w)
    threshold = best_f1_threshold(fit_y, apply_calibration(fit_raw, calibration), fit_w)

    # ⑤ 평가
    def evaluate(cal):
        return {
            "experience_eval": _metrics_or_empty(
                exp_y[~exp_train], apply_calibration(exp_raw[~exp_train], cal)
            ),
            "public_b": probability_metrics(ref_y[~in_a], apply_calibration(ref_raw[~in_a], cal)),
        }

    report["base_version"] = base_version
    report["current"] = evaluate(current.calibration)
    report["candidate"] = evaluate(calibration)
    report["threshold"] = threshold
    failures = gate(report["current"], report["candidate"])

    # 단계 판단: 보정이 바뀌면 확률 사이의 비율이 달라져 단계가 바뀔 수 있다 (v2에서 실제로 있었음).
    # 자동 반영 전에 대표 흐름이 의도한 단계로 나오는지 확인한다.
    candidate = PurchasePredictor(release_dir(base_version, models_dir))
    candidate.calibration = {"model": current.calibration["model"], **calibration}
    candidate.base_probability = candidate.timeline([(0, "base")])[0]["probabilities"]["base"]
    mismatches = scenario_mismatches(candidate)
    report["stage_mismatches"] = [list(m) for m in mismatches]
    if mismatches:
        failures.append(
            "단계 판단 대표 흐름이 의도한 단계와 다름: "
            + ", ".join(f"{items} {seconds}초 → {stage}" for items, seconds, stage in mismatches[:3])
        )
    report["gate"] = {"passed": not failures, "failures": failures}
    if failures:
        report["stopped"] = "gate_failed"
        _save(report, dataset_dir)
        return report
    if dry_run:
        report["stopped"] = "dry_run"
        _save(report, dataset_dir)
        return report

    # ⑥ 등록
    version = next_version(models_dir)
    exp_eval = report["candidate"]["experience_eval"]
    metadata = {
        "created": date.today().isoformat(),
        "description": f"{base_version} 모델에 체험 데이터({dataset_version})를 더해 다시 보정",
        "based_on": base_version,
        "training_data": f"{base_version}와 같은 모델 파일 (다시 학습하지 않음)",
        "calibration_data": (
            f"RetailRocket valid 일반 고객 A 절반 + 체험 데이터 학습용 {usable}세션 "
            f"(체험 행 가중치 {EXPERIENCE_WEIGHT})"
        ),
        "evaluation": {
            "data": "체험 데이터 평가용(세션 해시 20%), RetailRocket valid 일반 고객 B 절반",
            "experience_log_loss": round(exp_eval["log_loss"], 6),
            "experience_mean_prediction": round(exp_eval["mean_prediction"], 6),
            "experience_positive_rate": round(exp_eval["positive_rate"], 6),
            "public_log_loss": round(report["candidate"]["public_b"]["log_loss"], 6),
            "threshold": round(threshold, 4),
        },
        "dataset": str(dataset_dir),
    }
    register_version(version, base_version, calibration, threshold, metadata, models_dir)
    report["registered"] = version

    # ⑦ 반영
    if config["auto_release"]:
        use_version(version, models_dir)
        report["released"] = version
    report["stopped"] = "released" if config["auto_release"] else "registered"
    _save(report, dataset_dir)
    return report


def _save(report, dataset_dir):
    (Path(dataset_dir) / "pipeline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


MESSAGES = {
    "retrain_disabled": "재학습 스위치가 꺼져 있습니다 (ml/pipeline_config.json의 retrain_enabled). 확인만 하려면 --dry-run",
    "not_enough_sessions": "학습에 쓸 수 있는 체험 세션이 부족합니다",
    "gate_failed": "등록 기준을 통과하지 못해 새 버전을 만들지 않았습니다",
    "dry_run": "등록 기준을 통과했습니다 (--dry-run이라 등록하지 않음)",
    "registered": "새 버전을 등록했습니다. 반영은 auto_release가 꺼져 있어 직접 하세요",
    "released": "새 버전을 등록하고 서비스에 반영했습니다. 실행 중인 백엔드는 몇 초 안에 새 버전을 씁니다",
}


def main():
    parser = argparse.ArgumentParser(description="배치 재학습 파이프라인")
    parser.add_argument("input", nargs="?", help="백엔드가 내보낸 기록 파일")
    parser.add_argument("--dry-run", action="store_true", help="스위치와 상관없이 평가까지만 하고 등록하지 않음")
    parser.add_argument("--build-reference", action="store_true", help="RetailRocket 참조 파일 만들기")
    args = parser.parse_args()

    if args.build_reference:
        path, count = build_reference()
        print(f"참조 파일 저장: {path} ({count:,}행)")
        return
    if not args.input:
        parser.error("기록 파일 경로가 필요합니다")
    if not REFERENCE_PATH.exists():
        raise SystemExit(f"참조 파일이 없습니다: {REFERENCE_PATH}. 먼저 --build-reference를 실행하세요.")

    report = run(args.input, dry_run=args.dry_run)
    stopped = report["stopped"]
    if "dataset" in report:
        d = report["dataset"]
        print(f"② 학습 데이터: 세션 {d['input_sessions']}개 중 {d['kept_sessions']}개 사용, 행 {d['rows']:,}개")
        print(f"③ 학습용 체험 세션 {report['usable_train_sessions']}개 (필요 {report['config']['min_sessions']}개)")
    if "candidate" in report:
        for name, label in [("experience_eval", "체험 평가용"), ("public_b", "RetailRocket B")]:
            now, new = report["current"][name], report["candidate"][name]
            if "log_loss" in new:
                print(
                    f"⑤ {label}: Log loss {now['log_loss']:.5f} → {new['log_loss']:.5f}, "
                    f"평균 예측 {now['mean_prediction']:.3%} → {new['mean_prediction']:.3%} "
                    f"(실제 {new['positive_rate']:.3%})"
                )
        for failure in report["gate"]["failures"]:
            print(f"   - {failure}")
    if "registered" in report:
        print(f"⑥ 등록: {report['registered']}")
        if "released" not in report:
            print(f"   반영하려면: python ml/product_purchase/release.py use {report['registered']}")
    print(MESSAGES[stopped])


if __name__ == "__main__":
    main()
