"""조회 로그로 후보 상품별 구매 확률을 예측한다. 서비스 연결용 추론 모듈이다.

학습 데이터와 같은 UserViewState로 피처를 계산하고, ml/models/product_purchase_v1/의
확정 모델·보정·임계값을 사용한다. 입력에는 조회 로그만 사용하며 최종 선택·결제 정보는
넣지 않는다.

    predictor = PurchasePredictor()
    result = predictor.predict([(timestamp_ms, "A"), (timestamp_ms, "B"), ...])

명령줄에서는 timestamp, itemid 컬럼이 있는 CSV로 결과를 확인할 수 있다.

    python ml/product_purchase/predict.py log.csv
"""
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from events import ml_dir
from features import FEATURES, UserViewState
from modeling import apply_calibration


# 서비스에 쓰는 확정 모델. 학습 결과(ml/data/product_purchase/models/)와 달리 Git으로 관리한다.
RELEASE_DIR = ml_dir / "models" / "product_purchase_v1"


FEATURE_LABELS = {
    "view_count": "조회 횟수",
    "view_share": "전체 조회 중 비중",
    "seconds_since_first_view": "첫 조회 후 경과 시간",
    "seconds_since_last_view": "마지막 조회 후 경과 시간",
    "revisit_count": "다른 상품을 본 뒤 재방문 횟수",
    "user_total_views": "전체 조회 수",
    "distinct_items_viewed": "조회한 상품 수",
    "is_last_viewed": "가장 최근에 본 상품",
}


def to_milliseconds(values):
    """숫자는 밀리초로, 그 밖의 값은 날짜·시각으로 읽어 밀리초로 바꾼다."""
    series = pd.Series(values)
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("int64").to_numpy()
    times = pd.to_datetime(series, utc=True)
    return ((times - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)).to_numpy()


class PurchasePredictor:
    def __init__(self, directory=RELEASE_DIR):
        directory = Path(directory)
        self.calibration = json.loads(
            (directory / "calibration.json").read_text(encoding="utf-8")
        )
        self.model = lgb.Booster(
            model_file=str(directory / f"{self.calibration['model']}.txt")
        )
        self.threshold = self.calibration["threshold"]

    def _replay(self, views, purchases=()):
        """조회를 시간순으로 반영하며 예측 시점마다 (시각, 조회한 상품, 상태, 상품 ID 표)를 낸다.

        같은 시각의 조회는 한 예측 시점으로 묶는다. 상품 ID는 문자열이어도 되도록
        내부 번호로 바꿔 처리한다. purchases는 (시각, 상품 ID) 목록이다.
        """
        if isinstance(views, pd.DataFrame):
            frame = views[["timestamp", "itemid"]].copy()
        else:
            frame = pd.DataFrame(list(views), columns=["timestamp", "itemid"])
        if frame.empty:
            raise ValueError("조회 기록이 없습니다.")
        frame["timestamp"] = to_milliseconds(frame["timestamp"])
        frame = frame.sort_values("timestamp", kind="stable")

        purchases = pd.DataFrame(list(purchases), columns=["timestamp", "itemid"])
        if len(purchases):
            purchases["timestamp"] = to_milliseconds(purchases["timestamp"])
            purchases = purchases.sort_values("timestamp", kind="stable")

        code_of = {}
        for item in [*frame["itemid"], *purchases["itemid"]]:
            code_of.setdefault(item, len(code_of))
        item_of = {code: item for item, code in code_of.items()}

        pending = list(zip(purchases["timestamp"], purchases["itemid"]))
        state = UserViewState()
        index = 0
        for now, group in frame.groupby("timestamp", sort=True):
            now = int(now)
            while index < len(pending) and pending[index][0] <= now:
                state.mark_purchased(code_of[pending[index][1]])
                index += 1
            state.add_views(now, [code_of[item] for item in group["itemid"]])
            yield now, list(group["itemid"]), state, item_of

    def _score(self, state, now):
        positions = state.candidates()
        features = pd.DataFrame(state.features(now, positions))[FEATURES]
        if len(positions) == 0:
            # 조회한 상품을 모두 구매했다면 예측할 후보가 없다.
            return positions, features, np.empty(0)
        raw = self.model.predict(features)
        probability = apply_calibration(raw, self.calibration)
        return positions, features, probability

    def predict(self, views, purchases=()):
        """마지막 조회 시점의 후보별 확률·판정·순위·피처·SHAP 기여도.

        SHAP 기여도는 보정 전 모델 점수(로그 오즈)에 대한 값이다. 보정은 단조 증가이므로
        기여 방향은 확률에도 그대로 적용되지만, 합이 보정 확률과 같지는 않다.
        """
        for now, _, state, item_of in self._replay(views, purchases):
            pass
        positions, features, probability = self._score(state, now)
        contributions = (
            self.model.predict(features, pred_contrib=True)
            if len(positions)
            else np.empty((0, len(FEATURES) + 1))
        )
        order = np.argsort(-probability, kind="stable")
        rank = np.empty(len(order), dtype=int)
        rank[order] = np.arange(1, len(order) + 1)

        candidates = []
        for k in order:
            candidates.append(
                {
                    "item_id": item_of[int(state.items[positions[k]])],
                    "probability": float(probability[k]),
                    "decision": "구매 예상" if probability[k] >= self.threshold else "미구매 예상",
                    "rank": int(rank[k]),
                    "features": {
                        name: float(features[name].iloc[k]) for name in FEATURES
                    },
                    "shap": {
                        "base_value": float(contributions[k, -1]),
                        "contributions": {
                            name: float(value)
                            for name, value in zip(FEATURES, contributions[k, :-1])
                        },
                    },
                }
            )
        purchased = [
            item_of[int(state.items[pos])]
            for pos in range(state.size)
            if state.purchased[pos]
        ]
        return {
            "predicted_at": now,
            "threshold": self.threshold,
            "candidates": candidates,
            "purchased": purchased,
        }

    def timeline(self, views, purchases=()):
        """조회를 하나씩 재생하며 예측 시점마다 후보별 확률을 기록한다."""
        snapshots = []
        for now, viewed, state, item_of in self._replay(views, purchases):
            positions, _, probability = self._score(state, now)
            snapshots.append(
                {
                    "timestamp": now,
                    "viewed": viewed,
                    "probabilities": {
                        item_of[int(state.items[pos])]: float(p)
                        for pos, p in zip(positions, probability)
                    },
                }
            )
        return snapshots


def main():
    if len(sys.argv) != 2:
        raise SystemExit("사용법: python ml/product_purchase/predict.py log.csv")
    views = pd.read_csv(sys.argv[1])
    predictor = PurchasePredictor()

    print("조회별 확률 변화")
    start = None
    for snapshot in predictor.timeline(views):
        start = snapshot["timestamp"] if start is None else start
        minutes = (snapshot["timestamp"] - start) / 60000
        probabilities = " | ".join(
            f"{item} {p:.2%}" for item, p in snapshot["probabilities"].items()
        )
        print(f"  +{minutes:.1f}분 {', '.join(map(str, snapshot['viewed']))} 조회 → {probabilities}")

    result = predictor.predict(views)
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
