"""조회·장바구니 로그로 후보 상품별 구매 확률을 예측한다 (판매자용 모델 v3부터).

학습 데이터(build_extended_rows.py)와 같은 UserEventState로 피처를 계산하고, 버전 폴더의
모델·보정·임계값과 train 기간 상품 통계(item_stats.parquet)를 사용한다.
구매 기록은 후보 제외(구매 완료)에만 사용한다. 상품 ID는 RetailRocket itemid(정수)다.

    predictor = ExtendedPredictor(release_dir("v3"))
    result = predictor.predict([(timestamp_ms, "view", 355908), (timestamp_ms, "addtocart", 355908), ...])

명령줄에서는 timestamp, event(view/addtocart), itemid 컬럼이 있는 CSV로 결과를 확인할 수 있다.

    python ml/product_purchase/predict_extended.py log.csv v3
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

import item_stats
from features_extended import UserEventState
from modeling import apply_calibration
from predict import FEATURE_LABELS as VIEW_FEATURE_LABELS
from predict import to_milliseconds
from release import release_dir


EVENTS = ("view", "addtocart")
ITEM_STATS_FILE = "item_stats.parquet"

FEATURE_LABELS = {
    **VIEW_FEATURE_LABELS,
    "cart_count": "장바구니에 담은 횟수",
    "seconds_since_last_cart": "마지막으로 담은 뒤 경과 시간",
    "user_carted_items": "고객이 담은 상품 수",
    "item_viewers": "상품을 본 사람 수",
    "item_purchase_rate": "상품의 구매율",
    "item_cart_rate": "상품의 담기율",
}


class ExtendedPredictor:
    def __init__(self, directory):
        directory = Path(directory)
        self.version = directory.name
        self.metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        if self.metadata.get("input") != "view_cart":
            raise ValueError(f"조회·장바구니 입력 모델이 아닙니다: {directory}")
        self.features = self.metadata["features"]
        self.calibration = json.loads(
            (directory / "calibration.json").read_text(encoding="utf-8")
        )
        self.model = lgb.Booster(
            model_file=str(directory / f"{self.calibration['model']}.txt")
        )
        self.threshold = self.calibration["threshold"]
        self.item_stats = pd.read_parquet(directory / ITEM_STATS_FILE).set_index("itemid")
        self.item_stats_defaults = self.metadata["item_stats_defaults"]

    def _replay(self, events, purchases=()):
        """조회·담기를 시간순으로 반영하며 예측 시점마다 (시각, 이번 기록, 상태, 상품 ID 표)를 낸다.

        같은 시각의 기록은 한 예측 시점으로 묶는다. 상품 ID는 상품 통계를 찾는 데 쓰므로
        학습 데이터와 같은 RetailRocket itemid여야 통계가 붙는다 (없으면 전체 평균).
        """
        if isinstance(events, pd.DataFrame):
            frame = events[["timestamp", "event", "itemid"]].copy()
        else:
            frame = pd.DataFrame(list(events), columns=["timestamp", "event", "itemid"])
        if frame.empty:
            raise ValueError("조회·담기 기록이 없습니다.")
        unknown = set(frame["event"]) - set(EVENTS)
        if unknown:
            raise ValueError(f"알 수 없는 이벤트: {sorted(unknown)}")
        frame["timestamp"] = to_milliseconds(frame["timestamp"])
        frame = frame.sort_values("timestamp", kind="stable")

        purchases = pd.DataFrame(list(purchases), columns=["timestamp", "itemid"])
        if len(purchases):
            purchases["timestamp"] = to_milliseconds(purchases["timestamp"])
            purchases = purchases.sort_values("timestamp", kind="stable")

        pending = list(zip(purchases["timestamp"], purchases["itemid"]))
        state = UserEventState()
        index = 0
        for now, group in frame.groupby("timestamp", sort=True):
            now = int(now)
            while index < len(pending) and pending[index][0] <= now:
                state.mark_purchased(pending[index][1])
                index += 1
            is_cart = (group["event"] == "addtocart").to_numpy()
            items = group["itemid"].to_numpy()
            state.add_events(now, items[~is_cart].tolist(), items[is_cart].tolist())
            yield now, list(zip(group["event"], group["itemid"])), state

    def _frame(self, state, now):
        positions = state.candidates()
        values = state.features(now, positions)
        stats = self.item_stats.reindex(state.items[positions].tolist())
        for name in item_stats.COLUMNS:
            values[name] = stats[name].fillna(self.item_stats_defaults[name]).to_numpy(np.float32)
        return positions, pd.DataFrame(values)[self.features]

    def _score(self, state, now):
        positions, features = self._frame(state, now)
        if len(positions) == 0:
            return positions, features, np.empty(0)
        raw = self.model.predict(features)
        return positions, features, apply_calibration(raw, self.calibration)

    def predict(self, events, purchases=()):
        """마지막 기록 시점의 후보별 확률·판정·순위·피처·SHAP 기여도.

        SHAP 기여도는 보정 전 모델 점수(로그 오즈)에 대한 값이다. 기여 방향은 확률에도
        그대로 적용되지만, 합이 보정 확률과 같지는 않다.
        """
        for now, _, state in self._replay(events, purchases):
            pass
        positions, features, probability = self._score(state, now)
        contributions = (
            self.model.predict(features, pred_contrib=True)
            if len(positions)
            else np.empty((0, len(self.features) + 1))
        )
        order = np.argsort(-probability, kind="stable")
        candidates = []
        for rank, k in enumerate(order, start=1):
            candidates.append(
                {
                    "item_id": state.items[positions[k]].item(),
                    "probability": float(probability[k]),
                    "decision": "구매 예상" if probability[k] >= self.threshold else "미구매 예상",
                    "rank": rank,
                    "features": {
                        name: float(features[name].iloc[k]) for name in self.features
                    },
                    "shap": {
                        "base_value": float(contributions[k, -1]),
                        "contributions": {
                            name: float(value)
                            for name, value in zip(self.features, contributions[k, :-1])
                        },
                    },
                }
            )
        purchased = [
            state.items[pos].item() for pos in range(state.size) if state.purchased[pos]
        ]
        return {
            "predicted_at": now,
            "threshold": self.threshold,
            "candidates": candidates,
            "purchased": purchased,
        }

    def timeline(self, events, purchases=()):
        """기록을 하나씩 재생하며 예측 시점마다 후보별 확률을 기록한다."""
        snapshots = []
        for now, touched, state in self._replay(events, purchases):
            positions, _, probability = self._score(state, now)
            snapshots.append(
                {
                    "timestamp": now,
                    "events": [{"event": e, "item_id": i} for e, i in touched],
                    "probabilities": {
                        state.items[pos].item(): float(p) for pos, p in zip(positions, probability)
                    },
                }
            )
        return snapshots


def main():
    if len(sys.argv) != 3:
        raise SystemExit("사용법: python ml/product_purchase/predict_extended.py log.csv v3")
    events = pd.read_csv(sys.argv[1])
    predictor = ExtendedPredictor(release_dir(sys.argv[2]))

    print("기록별 확률 변화")
    start = None
    for snapshot in predictor.timeline(events):
        start = snapshot["timestamp"] if start is None else start
        minutes = (snapshot["timestamp"] - start) / 60000
        touched = ", ".join(f"{e['item_id']} {e['event']}" for e in snapshot["events"])
        probabilities = " | ".join(
            f"{item} {p:.2%}" for item, p in snapshot["probabilities"].items()
        )
        print(f"  +{minutes:.1f}분 {touched} → {probabilities}")

    result = predictor.predict(events)
    print(f"\n최종 예측 (임계값 {result['threshold']:.2%})")
    for candidate in result["candidates"]:
        contributions = sorted(
            candidate["shap"]["contributions"].items(), key=lambda x: -abs(x[1])
        )[:3]
        reasons = ", ".join(
            f"{FEATURE_LABELS[name]} {'+' if value >= 0 else ''}{value:.2f}"
            for name, value in contributions
        )
        print(
            f"  {candidate['rank']}위 {candidate['item_id']}: {candidate['probability']:.2%} "
            f"({candidate['decision']}) / 주요 기여: {reasons}"
        )


if __name__ == "__main__":
    main()
