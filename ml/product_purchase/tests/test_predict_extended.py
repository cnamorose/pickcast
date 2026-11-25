"""predict_extended.py를 Git에 포함된 조회·장바구니 모델(input: view_cart)로 확인한다.

학습 데이터(ml/data/product_purchase_time/extended_rows/)가 있으면 그 행의 피처를 예측 모듈이
원본 기록에서 다시 계산한 값과 대조한다. 없으면 그 테스트는 건너뛴다.
"""
import unittest

import numpy as np
import pyarrow.parquet as pq

import item_stats
from events import load_events, ml_dir
from predict import PurchasePredictor
from predict_extended import ExtendedPredictor
from release import list_versions, release_dir


MINUTE = 60_000
ROWS_PATH = ml_dir / "data" / "product_purchase_time" / "extended_rows" / "test.parquet"
SAMPLE_USERS = 30


def extended_versions():
    return [v["version"] for v in list_versions() if v["input"] == "view_cart" and v["problem"] is None]


@unittest.skipUnless(extended_versions(), "조회·장바구니 모델 버전이 없습니다")
class ExtendedPredictorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = ExtendedPredictor(release_dir(extended_versions()[-1]))
        # train 기간에 많이 본 상품 (통계가 있는 상품)
        cls.known = int(cls.predictor.item_stats["item_viewers"].idxmax())

    def probabilities(self, events, purchases=()):
        result = self.predictor.predict(events, purchases)
        return {c["item_id"]: c["probability"] for c in result["candidates"]}

    def test_cart_raises_probability(self):
        viewed = self.probabilities([(0, "view", self.known), (MINUTE, "view", 2)])
        carted = self.probabilities(
            [(0, "view", self.known), (MINUTE, "view", 2), (2 * MINUTE, "addtocart", self.known)]
        )
        self.assertGreater(carted[self.known], viewed[self.known] * 3)

    def test_cart_only_item_is_candidate(self):
        probabilities = self.probabilities([(0, "view", 1), (MINUTE, "addtocart", 2)])
        self.assertEqual(set(probabilities), {1, 2})

    def test_purchased_item_is_removed(self):
        result = self.predictor.predict(
            [(0, "view", 1), (MINUTE, "view", 2), (3 * MINUTE, "view", 3)],
            purchases=[(2 * MINUTE, 1)],
        )
        self.assertEqual({c["item_id"] for c in result["candidates"]}, {2, 3})
        self.assertEqual(result["purchased"], [1])

    def test_unknown_item_uses_defaults(self):
        unknown = -1
        candidate = self.predictor.predict([(0, "view", unknown)])["candidates"][0]
        for name in item_stats.COLUMNS:
            self.assertAlmostEqual(
                candidate["features"][name], self.predictor.item_stats_defaults[name], places=6
            )

    def test_output_shape(self):
        result = self.predictor.predict([(0, "view", 1), (MINUTE, "addtocart", 2)])
        self.assertEqual([c["rank"] for c in result["candidates"]], [1, 2])
        for candidate in result["candidates"]:
            self.assertTrue(0 <= candidate["probability"] <= 1)
            self.assertEqual(set(candidate["features"]), set(self.predictor.features))
            self.assertEqual(set(candidate["shap"]["contributions"]), set(self.predictor.features))
        timeline = self.predictor.timeline([(0, "view", 1), (MINUTE, "addtocart", 2)])
        self.assertEqual(len(timeline), 2)

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(ValueError):
            self.predictor.predict([(0, "transaction", 1)])

    def test_view_predictor_refuses_extended_version(self):
        with self.assertRaises(ValueError):
            PurchasePredictor(release_dir(self.predictor.version))


@unittest.skipUnless(extended_versions(), "조회·장바구니 모델 버전이 없습니다")
@unittest.skipUnless(ROWS_PATH.exists(), "확장 학습 데이터가 없습니다 (build_extended_rows.py)")
class MatchesTrainingRowsTest(unittest.TestCase):
    """test 사용자 몇 명의 마지막 예측 시점을 원본 기록에서 다시 계산해 학습 행과 대조한다."""

    def test_features_and_probabilities_match(self):
        predictor = ExtendedPredictor(release_dir(extended_versions()[-1]))
        columns = ["visitorid", "cutoff_timestamp", "itemid", *predictor.features]
        rows = pq.read_table(ROWS_PATH, columns=columns).to_pandas()
        rng = np.random.default_rng(7)
        users = rng.choice(rows["visitorid"].unique(), SAMPLE_USERS, replace=False)
        rows = rows[rows["visitorid"].isin(users)]

        events, _ = load_events()
        events = events[events["visitorid"].isin(users)]
        for uid, user_rows in rows.groupby("visitorid"):
            cutoff = user_rows["cutoff_timestamp"].max()
            expected = user_rows[user_rows["cutoff_timestamp"] == cutoff].set_index("itemid")
            mine = events[(events["visitorid"] == uid) & (events["timestamp"] <= cutoff)]
            touches = mine[mine["event"].isin(["view", "addtocart"])]
            buys = mine[mine["event"] == "transaction"]
            result = predictor.predict(
                touches[["timestamp", "event", "itemid"]].astype({"event": str}),
                list(zip(buys["timestamp"], buys["itemid"])),
            )
            with self.subTest(visitor=uid):
                got = {c["item_id"]: c["features"] for c in result["candidates"]}
                self.assertEqual(set(got), set(expected.index))
                for item, features in got.items():
                    for name in predictor.features:
                        np.testing.assert_allclose(
                            features[name], expected.loc[item, name], rtol=1e-5, err_msg=name
                        )


if __name__ == "__main__":
    unittest.main()
