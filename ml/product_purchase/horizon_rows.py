"""10분 예상 판매량의 분포 만들기(fit_purchase_hazard.py)와 확인(evaluate_horizon.py)에 쓰는 행 준비.

학습 데이터 행(예측 시점별 후보 상품)에 모델 확률, 첫 구매 시각, 같은 사용자의 다음 예측 시점을
붙인다. 행 하나는 "다음 예측 시점이 오기 전까지" 그 고객의 최신 상태다.
"""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from events import first_purchase_times
from modeling import apply_calibration, extended_rows_dir, load_split
from split_by_time import TEST_START, VALID_START

MINUTE = 60_000
NEVER = np.iinfo(np.int64).max // 4


def predict_split(directory, split, extra_columns=()):
    """버전 폴더의 모델·보정으로 구간 행의 확률을 계산한다."""
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    calibration = json.loads((directory / "calibration.json").read_text(encoding="utf-8"))
    model = lgb.Booster(model_file=str(directory / f"{calibration['model']}.txt"))
    features = metadata["features"]
    frame = load_split(split, features, extended_rows_dir, extra_columns)
    p = apply_calibration(model.predict(frame[features]), calibration)
    return frame, p


def purchase_times(frame, events):
    """행마다 그 사용자·상품의 첫 구매 시각 (정답 0인 행은 NEVER)."""
    first = first_purchase_times(events)
    labels = frame["label"].to_numpy() == 1
    bought = np.full(len(frame), NEVER, dtype=np.int64)
    bought[labels] = first.reindex(
        list(zip(frame.loc[labels, "visitorid"], frame.loc[labels, "itemid"]))
    ).to_numpy()
    cutoff = frame["cutoff_timestamp"].to_numpy()
    if (bought[labels] <= cutoff[labels]).any():
        raise ValueError("정답 1인 행의 구매 시각이 예측 시점 뒤에 없습니다.")
    return bought


def next_point_times(frame):
    """행마다 같은 사용자의 다음 예측 시점 시각 (없으면 NEVER). 한 시점의 행은 연속이다."""
    visitor = frame["visitorid"].to_numpy()
    cutoff = frame["cutoff_timestamp"].to_numpy()
    new_point = np.r_[True, (visitor[1:] != visitor[:-1]) | (cutoff[1:] != cutoff[:-1])]
    starts = np.flatnonzero(new_point)
    point_visitor, point_cutoff = visitor[starts], cutoff[starts]
    same_user = np.r_[point_visitor[1:] == point_visitor[:-1], False]
    if (np.diff(point_cutoff)[same_user[:-1]] <= 0).any():
        raise ValueError("사용자의 예측 시점이 시간순이 아닙니다.")
    point_next = np.where(same_user, np.r_[point_cutoff[1:], NEVER], NEVER)
    return point_next[np.cumsum(new_point) - 1]


def window_pairs(frame, bought, start, windows, step, active_minutes, chunk_rows=200_000):
    """10분 간격 시각 t_k = start + k × step마다 그때 최신 상태인 (후보 행, t) 쌍을 나눠 돌려준다.

    행은 예측 시점부터 다음 예측 시점, 구매, 마지막 행동 뒤 active_minutes, 마지막 구간 끝 중
    가장 빠른 때까지 최신 상태다. 쌍마다 (행 번호, k, 경과 분, 판매 여부)를 낸다.
    판매 여부는 (t, t + step] 안에 그 상품이 팔렸는지다. 그 사이 고객이 무엇을 했는지는 묻지 않는다.
    """
    cutoff = frame["cutoff_timestamp"].to_numpy()
    end = np.minimum.reduce([
        next_point_times(frame), cutoff + active_minutes * MINUTE, bought,
        np.full_like(cutoff, start + windows * step),
    ])
    first_k = np.maximum(-((start - cutoff) // step), 0)  # t_k >= cutoff 인 첫 k (올림)
    end_k = -((start - end) // step)                     # t_k < end 인 마지막 k + 1
    count = np.clip(end_k - first_k, 0, None)
    for lo in range(0, len(frame), chunk_rows):
        hi = min(lo + chunk_rows, len(frame))
        n = count[lo:hi]
        row = np.repeat(np.arange(lo, hi), n)
        if len(row) == 0:
            continue
        k = first_k[row] + np.arange(len(row)) - np.repeat(np.cumsum(n) - n, n)
        t = start + k * step
        elapsed = (t - cutoff[row]) / MINUTE
        sold = bought[row] <= t + step  # t < bought는 end에서 보장
        yield row, k, elapsed, sold


def period_bounds(split, events, frame):
    """구간의 시작·끝 시각. test는 데이터가 끝나는 시각(그 구간 사용자의 마지막 기록)까지다."""
    if split == "valid":
        return VALID_START, TEST_START
    if split == "test":
        users = pd.unique(frame["visitorid"])
        return TEST_START, int(events.loc[events["visitorid"].isin(users), "timestamp"].max()) + 1
    raise ValueError(split)
