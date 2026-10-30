"""피크타임 트래픽 우선 처리 시뮬레이션 (확장 기능 3).

서버가 감당 못 할 만큼 요청이 몰렸을 때, 구매 확률이 높은 고객의 요청을 먼저 처리하면
선착순보다 실제로 산 고객을 더 많이 지킬 수 있는지 RetailRocket 기록을 재생해 비교한다.
실제 서버에 부하를 걸지 않는다.

재생 방법
- 조회 시점 하나 = 서버 요청 하나. 요청의 우선순위 점수는 그 시점 고객의 구매 확률 중 최댓값을
  기준 확률 대비 배수(lift)로 바꾼 값이다 (서비스 모델, stage.py와 같은 기준).
- 가장 붐비는 시간대 WINDOWS개를 골라, 1시간을 COMPRESSED_SECONDS초로 압축해 각각 재생한다.
- 서버는 1초에 (평균 도착 수 ÷ OVERLOAD)개만 처리한다. 항상 OVERLOAD배 과부하가 걸린다.
- TIMEOUT_SECONDS 넘게 기다린 요청의 고객은 떠난다. 그 고객의 이후 요청도 들어오지 않는다.

처리 방식
- fifo: 먼저 온 요청부터
- priority: 점수가 높은 요청부터 (aging=0)
- aging: 점수 + α × 기다린 시간이 높은 요청부터. 오래 기다린 요청도 결국 처리된다.
  모든 요청이 같은 속도로 나이를 먹으므로 "점수 − α × 도착 시각"으로 정렬해도 순서가 같다.
  그래서 힙에 한 번 넣은 뒤 다시 정렬할 필요가 없다.

지표
- 지킨 구매 고객 비율: 재생 구간에서 결국 산 고객(이후 정답 1이 있는 고객) 중 떠나지 않은 비율
- 확률 낮은 고객(점수 LOW_SCORE 미만 요청을 낸 고객)이 떠난 비율, 처리된 요청의 평균·최대 대기

α는 valid로 정하고 test로 한 번 확인한다.

    python ml/product_purchase/peak_simulation.py
"""
import heapq
import json
import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from events import ml_dir, output_dir
from features import FEATURES
from modeling import apply_calibration, load_split
from predict import PurchasePredictor

WINDOWS = 100
COMPRESSED_SECONDS = 60
OVERLOAD = 1.5
TIMEOUT_SECONDS = 10
LOW_SCORE = 1.5
# 처음에는 2.0까지만 봤는데 선택 기준을 만족하는 α가 없어 큰 값을 추가했다 (기준은 그대로).
# α가 커질수록 선착순에 가까워진다.
ALPHAS = [0.0, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]
# α 선택 기준: 확률 낮은 고객이 떠난 비율이 선착순보다 이만큼(%p) 넘게 늘지 않는 α 중
# 지킨 구매 고객 비율이 가장 높은 것. 같으면 더 공평한(큰) α.
MAX_EXTRA_LOW_LEAVE = 0.05

REPORT_PATH = output_dir / "peak_simulation.json"
# 결과 API(백엔드)가 읽는 요약. 숫자만 담긴 작은 파일이라 Git으로 관리한다.
RESULTS_PATH = ml_dir / "results" / "peak_simulation.json"


@dataclass
class Request:
    arrival: float  # 압축된 시간(초)
    user: int
    score: float  # 기준 확률 대비 배수
    buyer: bool  # 이 고객이 결국 사는지 (재생 구간 안의 정답)


def priority_key(request, policy, alpha):
    """힙에서 작을수록 먼저 처리된다."""
    if policy == "fifo":
        return request.arrival
    return -(request.score - alpha * request.arrival)


def simulate(requests, capacity_per_second, policy, alpha=0.0, timeout=TIMEOUT_SECONDS):
    """요청을 1초 단위로 처리한다. 고객별로 떠났는지와 처리된 요청의 대기 시간을 돌려준다."""
    requests = sorted(requests, key=lambda r: r.arrival)
    left_users = set()
    waits = []  # (score, wait)
    heap, by_arrival = [], deque()
    done = set()  # 처리됐거나 버려진 요청 번호
    tokens = 0.0
    index = 0
    tick = 0
    while index < len(requests) or len(done) < len(requests):
        tick += 1
        while index < len(requests) and requests[index].arrival < tick:
            request = requests[index]
            if request.user in left_users:
                done.add(index)
            else:
                heapq.heappush(heap, (priority_key(request, policy, alpha), index))
                by_arrival.append(index)
            index += 1

        # 너무 오래 기다린 요청의 고객은 떠난다
        while by_arrival and tick - requests[by_arrival[0]].arrival > timeout:
            k = by_arrival.popleft()
            if k not in done:
                done.add(k)
                left_users.add(requests[k].user)
        for k in list(by_arrival):
            if k not in done and requests[k].user in left_users:
                done.add(k)

        tokens += capacity_per_second
        while tokens >= 1 and heap:
            _, k = heapq.heappop(heap)
            if k in done:
                continue
            done.add(k)
            tokens -= 1
            waits.append((requests[k].score, tick - requests[k].arrival))
        if not heap:
            tokens = min(tokens, capacity_per_second)  # 쉬는 동안 처리량을 쌓아 두지 않는다
        if index >= len(requests) and not heap:
            break
    return left_users, waits


def window_requests(points, start, end):
    """한 시간 구간의 요청을 압축된 시간으로 바꾼다."""
    rows = {name: values[start:end] for name, values in points.items()}
    scale = COMPRESSED_SECONDS / 3_600_000
    first = rows["cutoff"][0] - rows["cutoff"][0] % 3_600_000
    buyers = set(rows["visitor"][rows["label"] == 1].tolist())
    return [
        Request(float((c - first) * scale), int(v), float(s), int(v) in buyers)
        for c, v, s in zip(rows["cutoff"], rows["visitor"], rows["score"])
    ]


def load_points(split, predictor):
    """조회 시점(고객, 시각)별 점수(확률 최댓값의 lift)와 정답(그 시점 후보 중 산 것이 있는지)."""
    frame = load_split(split)
    p = apply_calibration(predictor.model.predict(frame[FEATURES]), predictor.calibration)
    visitor = frame["visitorid"].to_numpy()
    cutoff = frame["cutoff_timestamp"].to_numpy()
    starts = np.flatnonzero(np.r_[True, (visitor[1:] != visitor[:-1]) | (cutoff[1:] != cutoff[:-1])])
    score = np.maximum.reduceat(p, starts) / predictor.base_probability
    label = np.maximum.reduceat(frame["label"].to_numpy(), starts)
    order = np.argsort(cutoff[starts], kind="stable")
    return {
        "visitor": visitor[starts][order],
        "cutoff": cutoff[starts][order],
        "score": score[order],
        "label": label[order],
    }


def busiest_windows(points, count=WINDOWS):
    hour = points["cutoff"] // 3_600_000
    hours, counts = np.unique(hour, return_counts=True)
    top = hours[np.argsort(-counts, kind="stable")[:count]]
    bounds = []
    for h in sorted(top):
        lo, hi = np.searchsorted(hour, h), np.searchsorted(hour, h, side="right")
        bounds.append((lo, hi))
    return bounds


def evaluate(windows, policy, alpha):
    buyers = protected = low_users = low_left = 0
    low_waits, all_waits = [], []
    left_total = users_total = 0
    for requests in windows:
        capacity = len(requests) / COMPRESSED_SECONDS / OVERLOAD
        left, waits = simulate(requests, capacity, policy, alpha)
        users = {r.user for r in requests}
        buyer_users = {r.user for r in requests if r.buyer}
        low = {r.user for r in requests if r.score < LOW_SCORE} - {r.user for r in requests if r.score >= LOW_SCORE}
        buyers += len(buyer_users)
        protected += len(buyer_users - left)
        low_users += len(low)
        low_left += len(low & left)
        users_total += len(users)
        left_total += len(left)
        all_waits += [w for _, w in waits]
        low_waits += [w for s, w in waits if s < LOW_SCORE]
    return {
        "policy": policy,
        "alpha": alpha,
        "buyers": buyers,
        "protected_buyer_rate": protected / buyers if buyers else None,
        "users": users_total,
        "left_rate": left_total / users_total,
        "low_users": low_users,
        "low_left_rate": low_left / low_users if low_users else None,
        "low_wait_mean": float(np.mean(low_waits)) if low_waits else None,
        "low_wait_max": float(np.max(low_waits)) if low_waits else None,
        "wait_mean": float(np.mean(all_waits)) if all_waits else None,
    }


def run_split(split, predictor):
    points = load_points(split, predictor)
    windows = [window_requests(points, lo, hi) for lo, hi in busiest_windows(points)]
    results = [evaluate(windows, "fifo", 0.0)]
    results += [evaluate(windows, "aging" if a > 0 else "priority", a) for a in ALPHAS]
    return {"windows": len(windows), "requests": sum(len(w) for w in windows), "results": results}


def choose_alpha(valid):
    fifo = valid["results"][0]
    candidates = [
        r for r in valid["results"][1:]
        if r["low_left_rate"] <= fifo["low_left_rate"] + MAX_EXTRA_LOW_LEAVE
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda r: (round(r["protected_buyer_rate"], 4), r["alpha"]))
    return best["alpha"]


def main():
    if RESULTS_PATH.exists():
        raise SystemExit(f"이미 test까지 평가했습니다: {RESULTS_PATH}")
    predictor = PurchasePredictor()
    print("valid로 α를 정합니다.", flush=True)
    valid = run_split("valid", predictor)
    alpha = choose_alpha(valid)
    print_table("valid", valid)
    if alpha is None:
        raise SystemExit("선택 기준을 만족하는 α가 없습니다.")
    print(f"선택한 α: {alpha}", flush=True)

    print("\ntest로 한 번 확인합니다.", flush=True)
    test = run_split("test", predictor)
    print_table("test", test)

    settings = {
        "model_version": predictor.version,
        "windows": WINDOWS,
        "compressed_seconds_per_hour": COMPRESSED_SECONDS,
        "overload": OVERLOAD,
        "timeout_seconds": TIMEOUT_SECONDS,
        "low_score": LOW_SCORE,
        "alphas": ALPHAS,
        "max_extra_low_leave": MAX_EXTRA_LOW_LEAVE,
        "chosen_alpha": alpha,
    }
    report = {"settings": settings, "valid": valid, "test": test}
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def pick(split, policy, a):
        return next(r for r in split["results"] if r["policy"] == policy and math.isclose(r["alpha"], a))

    summary = {
        "settings": settings,
        "test": {
            "fifo": pick(test, "fifo", 0.0),
            "priority": pick(test, "priority", 0.0),
            "aging": pick(test, "aging" if alpha > 0 else "priority", alpha),
        },
        "valid_alpha_curve": valid["results"],
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {REPORT_PATH}\n요약 저장: {RESULTS_PATH}")


def print_table(name, split):
    print(f"[{name}] 구간 {split['windows']}개, 요청 {split['requests']:,}개")
    print(f"  {'방식':<10}{'α':>6}{'지킨 구매 고객':>14}{'전체 이탈':>10}{'저확률 이탈':>12}{'저확률 평균대기':>14}{'저확률 최대대기':>14}")
    for r in split["results"]:
        print(
            f"  {r['policy']:<10}{r['alpha']:>6}{r['protected_buyer_rate']:>14.1%}{r['left_rate']:>10.1%}"
            f"{r['low_left_rate']:>12.1%}{r['low_wait_mean']:>14.2f}{r['low_wait_max']:>14.1f}"
        )


if __name__ == "__main__":
    main()
