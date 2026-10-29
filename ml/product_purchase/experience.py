"""체험 기록을 학습 데이터로 바꾼다. 배치 재학습 파이프라인의 데이터 준비 단계다.

백엔드가 DB에서 내보낸 기록 파일(CSV 또는 Parquet)을 읽는다. ml 코드는 DB에 직접 접속하지 않는다.

    session_id, event(view/purchase), item_id, timestamp(ms), status, kind, mode

1. 정제: 학습에 쓰면 안 되는 세션을 빼고 이유를 리포트에 남긴다.
2. 학습 행: RetailRocket 학습 데이터(build_training_rows.py)와 같은 규칙으로 만든다.
   조회 시점마다 지금까지 본 상품을 후보로 한 행씩, 피처 8개(UserViewState)와
   정답(그 시점 이후 이 세션에서 그 상품을 결제했는가)을 붙인다.
3. 평가용 분리: 세션 ID 해시로 학습(train)·평가(eval)를 나눈다. 같은 세션은 항상 같은 쪽이다.
4. 저장: ml/data/experience/<날짜>/ 에 학습 행과 정제 리포트를 버전별로 남긴다.

    python ml/product_purchase/experience.py sessions.csv
"""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from events import HEAVY_USER_MIN_VIEWS, ml_dir
from features import FEATURES, UserViewState

EXPERIENCE_DIR = ml_dir / "data" / "experience"
COLUMNS = ["session_id", "event", "item_id", "timestamp", "status", "kind", "mode"]
NO_PURCHASE = np.iinfo(np.int64).max

# 정제 기준
FINISHED_STATUSES = {"purchased", "abandoned"}  # 쇼핑 중(active)은 정답이 정해지지 않음
TRAINING_MODES = {"experience"}  # 가상 손님 스크립트(simulated) 등은 뺀다
MAX_VIEWS = HEAVY_USER_MIN_VIEWS  # RetailRocket과 같은 과다 조회 기준
MIN_MEDIAN_GAP_MS = 1000  # 조회 간격 중앙값이 이보다 짧으면 사람이 아니라 스크립트로 본다
MIN_VIEWS_FOR_SPEED_CHECK = 3

EVAL_SHARE = 0.2


def load_records(path):
    path = Path(path)
    frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    missing = [c for c in COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"기록 파일에 없는 칸: {missing}")
    frame = frame[COLUMNS].copy()
    frame["session_id"] = frame["session_id"].astype(str)
    frame["item_id"] = frame["item_id"].astype(str)
    frame["timestamp"] = frame["timestamp"].astype("int64")
    return frame


def split_of(session_id):
    """세션 ID 해시로 학습·평가를 정한다. 저장하지 않아도 같은 세션은 항상 같은 쪽이다."""
    bucket = int(hashlib.sha1(session_id.encode()).hexdigest(), 16) % 100
    return "eval" if bucket < EVAL_SHARE * 100 else "train"


def clean_sessions(records):
    """정제 기준에 맞지 않는 세션을 빼고, 뺀 이유별 세션 수를 함께 돌려준다."""
    report = {"input_sessions": int(records["session_id"].nunique())}
    duplicated = records.duplicated(["session_id", "event", "item_id", "timestamp"])
    report["duplicate_rows_removed"] = int(duplicated.sum())
    records = records.loc[~duplicated]

    removed = {}
    keep = set()
    for session_id, group in records.groupby("session_id", sort=False):
        views = group.loc[group["event"] == "view"].sort_values("timestamp", kind="stable")
        reason = None
        if group["status"].iloc[0] not in FINISHED_STATUSES:
            reason = "not_finished"
        elif group["mode"].iloc[0] not in TRAINING_MODES:
            reason = "not_experience"
        elif len(views) == 0:
            reason = "no_views"
        elif len(views) >= MAX_VIEWS:
            reason = "too_many_views"
        elif (
            len(views) >= MIN_VIEWS_FOR_SPEED_CHECK
            and np.median(np.diff(views["timestamp"].to_numpy())) < MIN_MEDIAN_GAP_MS
        ):
            reason = "too_fast"
        if reason:
            removed[reason] = removed.get(reason, 0) + 1
        else:
            keep.add(session_id)

    report["removed_sessions"] = removed
    report["kept_sessions"] = len(keep)
    return records.loc[records["session_id"].isin(keep)], report


def session_rows(views, purchases):
    """한 세션의 학습 행. build_training_rows.py의 사용자별 처리와 같은 규칙이다.

    views, purchases: (timestamp, item_id) 목록. 상품 ID는 문자열이어도 된다.
    같은 시각에 조회와 구매가 함께 있으면 선후를 알 수 없어 그 예측 시점은 뺀다.
    """
    code_of = {}
    for _, item in [*views, *purchases]:
        code_of.setdefault(item, len(code_of))
    item_of = {code: item for item, code in code_of.items()}

    first_buy = {}
    for timestamp, item in purchases:
        first_buy[item] = min(timestamp, first_buy.get(item, NO_PURCHASE))
    pending = sorted((t, code_of[i]) for i, t in first_buy.items())
    buy_times = {t for t, _ in purchases}

    by_time = {}
    for timestamp, item in sorted(views, key=lambda v: v[0]):
        by_time.setdefault(timestamp, []).append(code_of[item])

    state = UserViewState()
    buy_of_position = []
    rows = []
    excluded_points = 0
    index = 0
    for now, codes in sorted(by_time.items()):
        while index < len(pending) and pending[index][0] <= now:
            state.mark_purchased(pending[index][1])
            index += 1
        size_before = state.size
        state.add_views(now, codes)
        for pos in range(size_before, state.size):
            buy_of_position.append(first_buy.get(item_of[int(state.items[pos])], NO_PURCHASE))

        positions = state.candidates()
        if now in buy_times:
            excluded_points += 1
            continue
        if len(positions) == 0:
            continue
        label = (np.asarray(buy_of_position)[positions] != NO_PURCHASE).astype(np.int8)
        features = state.features(now, positions)
        for k, pos in enumerate(positions):
            rows.append(
                {
                    "cutoff_timestamp": now,
                    "item_id": item_of[int(state.items[pos])],
                    **{name: features[name][k] for name in FEATURES},
                    "label": int(label[k]),
                }
            )
    return rows, excluded_points


def build_rows(records):
    """정제된 기록 전체를 학습 행 표로 만든다."""
    rows = []
    excluded_points = 0
    for session_id, group in records.groupby("session_id", sort=True):
        views = list(group.loc[group["event"] == "view", ["timestamp", "item_id"]].itertuples(index=False))
        purchases = list(
            group.loc[group["event"] == "purchase", ["timestamp", "item_id"]].itertuples(index=False)
        )
        session, excluded = session_rows([tuple(v) for v in views], [tuple(p) for p in purchases])
        excluded_points += excluded
        split = split_of(session_id)
        for row in session:
            rows.append({"session_id": session_id, "split": split, **row})
    columns = ["session_id", "split", "cutoff_timestamp", "item_id", *FEATURES, "label"]
    return pd.DataFrame(rows, columns=columns), excluded_points


def build_dataset(input_path, output_root=EXPERIENCE_DIR, version=None):
    """기록 파일을 정제하고 학습 행을 만들어 날짜별 폴더에 저장한다."""
    version = version or date.today().isoformat()
    target = Path(output_root) / version
    if target.exists():
        raise FileExistsError(f"이미 있는 데이터셋 버전입니다: {target}")

    records, report = clean_sessions(load_records(input_path))
    rows, excluded_points = build_rows(records)
    report["excluded_same_time_points"] = excluded_points
    report["rows"] = int(len(rows))
    report["positive_rows"] = int(rows["label"].sum()) if len(rows) else 0
    report["splits"] = {
        name: {
            "sessions": int(group["session_id"].nunique()),
            "rows": int(len(group)),
            "positive_rows": int(group["label"].sum()),
        }
        for name, group in rows.groupby("split")
    }
    report["input"] = str(input_path)

    target.mkdir(parents=True)
    rows.to_parquet(target / "training_rows.parquet", index=False)
    (target / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target, report


def main():
    parser = argparse.ArgumentParser(description="체험 기록을 학습 데이터로 바꾼다")
    parser.add_argument("input", help="백엔드가 내보낸 기록 파일 (CSV 또는 Parquet)")
    parser.add_argument("--version", help="데이터셋 버전 이름 (기본: 오늘 날짜)")
    args = parser.parse_args()

    target, report = build_dataset(args.input, version=args.version)
    print(f"세션 {report['input_sessions']}개 중 {report['kept_sessions']}개 사용")
    for reason, count in report["removed_sessions"].items():
        print(f"  제외 {reason}: {count}개")
    print(f"학습 행 {report['rows']:,}개 (정답 1: {report['positive_rows']:,}개)")
    for name, split in report["splits"].items():
        print(f"  {name}: 세션 {split['sessions']}개, 행 {split['rows']:,}개")
    print(f"저장: {target}")


if __name__ == "__main__":
    main()
