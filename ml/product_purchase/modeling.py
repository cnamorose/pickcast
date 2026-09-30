"""학습·평가에서 함께 쓰는 데이터 로드, 가중치, 평가 지표."""
import numpy as np
import pyarrow.parquet as pq
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from events import output_dir
from features import FEATURES


rows_dir = output_dir / "training_rows"
models_dir = output_dir / "models"

WEIGHTINGS = ["row", "point", "user"]


def load_split(name):
    """구간 데이터를 읽고 예측 시점별 후보 수와 사용자별 행 수를 붙인다."""
    table = pq.read_table(
        rows_dir / f"{name}.parquet",
        columns=["visitorid", "cutoff_timestamp", "itemid", "heavy_user", *FEATURES, "label"],
    )
    frame = table.to_pandas()
    del table

    # 생성 시 한 예측 시점의 행은 연속으로 저장된다.
    visitor = frame["visitorid"].to_numpy()
    cutoff = frame["cutoff_timestamp"].to_numpy()
    new_point = np.r_[True, (visitor[1:] != visitor[:-1]) | (cutoff[1:] != cutoff[:-1])]
    point_id = np.cumsum(new_point) - 1
    frame["candidate_count"] = np.bincount(point_id)[point_id].astype(np.int32)

    new_user = np.r_[True, visitor[1:] != visitor[:-1]]
    user_id = np.cumsum(new_user) - 1
    frame["user_row_count"] = np.bincount(user_id)[user_id].astype(np.int32)
    return frame


def row_weights(frame, weighting):
    """학습 행 가중치. 평균이 1이 되도록 맞춘다.

    row: 모든 행 1
    point: 예측 시점마다 합이 1 (조회 1회를 같은 무게로)
    user: 사용자마다 합이 1 (사용자를 같은 무게로)
    """
    if weighting == "row":
        weight = np.ones(len(frame), dtype=np.float64)
    elif weighting == "point":
        weight = 1.0 / frame["candidate_count"].to_numpy(dtype=np.float64)
    elif weighting == "user":
        weight = 1.0 / frame["user_row_count"].to_numpy(dtype=np.float64)
    else:
        raise ValueError(weighting)
    return weight / weight.mean()


def _metrics(y, p, weight=None, threshold=None):
    if len(y) == 0 or y.min() == y.max():
        return None
    p = np.clip(p, 1e-7, 1 - 1e-7)
    result = {
        "rows": int(len(y)),
        "positive_rows": int(y.sum()),
        "positive_rate": float(np.average(y, weights=weight)),
        "mean_prediction": float(np.average(p, weights=weight)),
        "ap": float(average_precision_score(y, p, sample_weight=weight)),
        "roc_auc": float(roc_auc_score(y, p, sample_weight=weight)),
        "log_loss": float(log_loss(y, p, sample_weight=weight)),
        "brier": float(brier_score_loss(y, p, sample_weight=weight)),
    }
    if threshold is not None:
        result.update(decision_metrics(y, p, threshold, weight))
    return result


def decision_metrics(y, p, threshold, weight=None):
    """확률이 threshold 이상이면 구매 예상으로 판정했을 때의 정밀도·재현율·F1."""
    w = np.ones(len(y)) if weight is None else weight
    predicted = p >= threshold
    tp = w[predicted & (y == 1)].sum()
    precision = tp / w[predicted].sum() if predicted.any() else 0.0
    recall = tp / w[y == 1].sum()
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    return {
        "predicted_positive_share": float(w[predicted].sum() / w.sum()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
    }


def best_f1_threshold(y, p, weight):
    """F1이 가장 높은 임계값. 같은 확률의 행은 함께 판정되도록 경계만 후보로 본다."""
    order = np.argsort(-p, kind="stable")
    p_sorted, y_sorted, w_sorted = p[order], y[order], weight[order]
    tp = np.cumsum(w_sorted * y_sorted)
    predicted = np.cumsum(w_sorted)
    last_of_value = np.r_[p_sorted[1:] != p_sorted[:-1], True]
    tp, predicted, values = tp[last_of_value], predicted[last_of_value], p_sorted[last_of_value]
    precision = tp / predicted
    recall = tp / tp[-1]
    total = precision + recall
    f1 = np.divide(2 * precision * recall, total, out=np.zeros_like(total), where=total > 0)
    best = int(np.argmax(f1))
    return float(values[best])


def reliability_table(y, p, weight, bins=10):
    """예측 확률 구간별 평균 예측과 실제 구매 비율. 구간은 가중 분위수로 나눈다."""
    order = np.argsort(p, kind="stable")
    cumulative = np.cumsum(weight[order]) / weight.sum()
    bin_of_sorted = np.minimum((cumulative * bins).astype(int), bins - 1)
    table = []
    for b in range(bins):
        idx = order[bin_of_sorted == b]
        if len(idx) == 0:
            continue
        w = weight[idx]
        table.append(
            {
                "min_prediction": float(p[idx].min()),
                "max_prediction": float(p[idx].max()),
                "mean_prediction": float(np.average(p[idx], weights=w)),
                "positive_rate": float(np.average(y[idx], weights=w)),
                "rows": int(len(idx)),
            }
        )
    return table


def reliability_by_edges(y, p, weight, edges):
    """정해진 확률 구간별 평균 예측과 실제 구매 비율."""
    table = []
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (p >= low) & (p < high)
        if not mask.any():
            continue
        w = weight[mask]
        table.append(
            {
                "range": [low, high],
                "rows": int(mask.sum()),
                "weight_share": float(w.sum() / weight.sum()),
                "mean_prediction": float(np.average(p[mask], weights=w)),
                "positive_rate": float(np.average(y[mask], weights=w)),
            }
        )
    return table


def point_weights(frame):
    """예측 시점마다 합이 1인 평가 가중치."""
    return 1.0 / frame["candidate_count"].to_numpy(dtype=np.float64)


def apply_calibration(raw, calibration):
    """calibration.json의 보정을 모델 점수에 적용한다."""
    if calibration["method"] == "platt":
        raw = np.clip(raw, 1e-12, 1 - 1e-12)
        z = calibration["slope"] * np.log(raw / (1 - raw)) + calibration["intercept"]
        return 1 / (1 + np.exp(-z))
    if calibration["method"] == "isotonic":
        return np.interp(raw, calibration["x"], calibration["y"])
    if calibration["method"] == "isotonic_smooth":
        raw = np.clip(raw, 1e-12, 1 - 1e-12)
        return np.interp(np.log(raw / (1 - raw)), calibration["x_logit"], calibration["y"])
    raise ValueError(calibration["method"])


def evaluate(frame, p, threshold=None):
    """여러 관점의 지표를 계산한다.

    point_weighted를 모델 선택 기준으로 사용한다. 행 단위 지표는 소수 과다 조회
    사용자에 의해 좌우되므로 참고용으로 함께 기록한다.
    """
    y = frame["label"].to_numpy()
    point_weight = point_weights(frame)
    heavy = frame["heavy_user"].to_numpy() == 1
    first_view = frame["user_total_views"].to_numpy() == 1
    return {
        "point_weighted": _metrics(y, p, point_weight, threshold),
        "rows": _metrics(y, p, None, threshold),
        "non_heavy_rows": _metrics(y[~heavy], p[~heavy], None, threshold),
        "heavy_rows": _metrics(y[heavy], p[heavy], None, threshold),
        "first_view_points": _metrics(y[first_view], p[first_view], None, threshold),
        "repeat_view_point_weighted": _metrics(
            y[~first_view], p[~first_view], point_weight[~first_view], threshold
        ),
    }


def summary_line(name, result):
    main = result["point_weighted"]
    non_heavy = result["non_heavy_rows"]
    return (
        f"{name:<16} 시점 가중 AP {main['ap']:.4f} / AUC {main['roc_auc']:.4f} | "
        f"과다 조회 제외 AP {non_heavy['ap']:.4f} / AUC {non_heavy['roc_auc']:.4f} | "
        f"행 단위 AP {result['rows']['ap']:.4f}"
    )


def log_features(frame):
    """로지스틱 회귀용: 치우친 수치 피처에 log1p를 적용한다."""
    x = frame[FEATURES].astype(np.float64).copy()
    for name in FEATURES:
        if name not in ("view_share", "is_last_viewed"):
            x[name] = np.log1p(x[name])
    return x.to_numpy()

