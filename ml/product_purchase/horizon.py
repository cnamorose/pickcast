"""모델의 "이후 언젠가 살 확률"을 "앞으로 10분 안에 살 확률"로 바꾼다 (판매자용 예상 판매량).

모델(v3)의 정답은 "예측 시점 이후 그 상품을 샀는가"라 기간이 없다. 시뮬레이션·게임은 "앞으로 10분
동안 몇 개 팔릴지"가 필요하므로, valid 기록으로 10분 판매 비율을 따로 구해 곱한다.

10분 판매 비율 r(e): valid 기간을 10분 간격으로 재생하며, 시각 t에 쇼핑 중인 고객의 후보 상품 중
마지막 행동 뒤 e분이 지난 것들이 (t, t+10분]에 실제로 팔린 수 ÷ 그 상품들의 모델 확률 합이다.
그 10분 사이 고객이 더 둘러보거나 담는 경우도 그대로 들어간다. 담은 상품과 담지 않은 상품은
따로 구한다. 시점마다 최신 상태 하나만 보므로 같은 구매를 여러 번 세지 않는다.

    10분 안에 살 확률 = min(1, p × r(e))

이미 들어와서 상품을 보거나 담은 고객만 예측한다. 아직 들어오지 않은 고객의 판매는 넣지 않는다.

    rates = load_rates(release_dir("v3"))
    q = within_horizon(p, elapsed_minutes, carted, rates)
"""
import json
from pathlib import Path

import numpy as np

HORIZON_MINUTES = 10
# 마지막 행동 뒤 이 시간이 지난 고객은 "지금 쇼핑 중"으로 보지 않는다 (예상 판매량에서 뺀다).
ACTIVE_MINUTES = 24 * 60
RATES_FILE = "horizon_rates.json"
GROUPS = ("carted", "not_carted")
# 판매 비율을 따로 재는 경과 시간 구간(분). 마지막 행동 직후에 많이 사서 앞쪽을 촘촘하게 둔다.
EDGES_MINUTES = [
    0, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 360, 480, 720, 960, ACTIVE_MINUTES,
]


def elapsed_bin(elapsed_minutes, edges=EDGES_MINUTES):
    """경과 시간이 속한 구간 번호. 범위를 벗어나면 첫·마지막 구간으로 붙인다."""
    index = np.searchsorted(edges, np.asarray(elapsed_minutes, dtype=float), side="right") - 1
    return np.clip(index, 0, len(edges) - 2)


class RateCounter:
    """(후보, 시각) 쌍을 받아 구간별 모델 확률 합과 판매 수를 센다."""

    def __init__(self, edges=EDGES_MINUTES):
        self.edges = list(edges)
        bins = len(edges) - 1
        self.sum_p = {name: np.zeros(bins) for name in GROUPS}
        self.sold = {name: np.zeros(bins) for name in GROUPS}

    def add(self, p, elapsed_minutes, carted, sold):
        b = elapsed_bin(elapsed_minutes, self.edges)
        carted = np.asarray(carted, dtype=bool)
        bins = len(self.edges) - 1
        for name, mask in (("carted", carted), ("not_carted", ~carted)):
            self.sum_p[name] += np.bincount(b[mask], weights=np.asarray(p)[mask], minlength=bins)
            self.sold[name] += np.bincount(b[mask], weights=np.asarray(sold, dtype=float)[mask], minlength=bins)

    def rates(self):
        result = {"edges_minutes": self.edges, "horizon_minutes": HORIZON_MINUTES}
        for name in GROUPS:
            if self.sold[name].sum() == 0:
                raise ValueError(f"{name} 판매가 없습니다.")
            sum_p = self.sum_p[name]
            result[name] = np.divide(
                self.sold[name], sum_p, out=np.zeros_like(sum_p), where=sum_p > 0
            ).round(6).tolist()
            result[f"{name}_sales"] = int(self.sold[name].sum())
            result[f"{name}_sum_p"] = round(float(sum_p.sum()), 2)
        return result


def within_horizon(p, elapsed_minutes, carted, rates):
    """예측 시점 확률 p를 "지금부터 10분 안에 살 확률"로 바꾼다.

    elapsed_minutes: 예측 시점(마지막 조회·담기)부터 지금까지 지난 시간. 그사이 사지 않았다고 본다.
    ACTIVE_MINUTES가 지난 후보는 0이다.
    """
    p = np.asarray(p, dtype=float)
    elapsed = np.asarray(elapsed_minutes, dtype=float)
    b = elapsed_bin(elapsed, rates["edges_minutes"])
    rate = np.where(
        np.asarray(carted, dtype=bool),
        np.asarray(rates["carted"])[b],
        np.asarray(rates["not_carted"])[b],
    )
    active = (elapsed >= 0) & (elapsed < rates["edges_minutes"][-1])
    return np.where(active, np.clip(p * rate, 0.0, 1.0), 0.0)


def load_rates(directory):
    path = Path(directory) / RATES_FILE
    if not path.exists():
        raise FileNotFoundError(f"10분 판매 비율이 없습니다: {path} (fit_horizon_rates.py)")
    return json.loads(path.read_text(encoding="utf-8"))
