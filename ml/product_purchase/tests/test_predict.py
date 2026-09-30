"""predict.py의 출력 형식과 일관성을 확인한다. Git에 포함된 확정 모델을 사용한다."""
import unittest

import numpy as np

from modeling import apply_calibration
from predict import PurchasePredictor


MINUTE = 60_000


class PurchasePredictorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = PurchasePredictor()
        cls.views = [
            (0, "A"),
            (2 * MINUTE, "B"),
            (3 * MINUTE, "C"),
            (5 * MINUTE, "A"),
            (6 * MINUTE, "B"),
            (8 * MINUTE, "A"),
        ]

    def test_candidates(self):
        result = self.predictor.predict(self.views)
        candidates = result["candidates"]
        self.assertEqual({c["item_id"] for c in candidates}, {"A", "B", "C"})
        self.assertEqual([c["rank"] for c in candidates], [1, 2, 3])
        probabilities = [c["probability"] for c in candidates]
        self.assertEqual(probabilities, sorted(probabilities, reverse=True))
        for c in candidates:
            self.assertTrue(0 <= c["probability"] <= 1)
            expected = "구매 예상" if c["probability"] >= result["threshold"] else "미구매 예상"
            self.assertEqual(c["decision"], expected)
        self.assertEqual(result["predicted_at"], 8 * MINUTE)

    def test_shap_sums_to_model_score(self):
        result = self.predictor.predict(self.views)
        for c in result["candidates"]:
            raw_score = c["shap"]["base_value"] + sum(c["shap"]["contributions"].values())
            raw = 1 / (1 + np.exp(-raw_score))
            calibrated = apply_calibration(np.array([raw]), self.predictor.calibration)[0]
            self.assertAlmostEqual(calibrated, c["probability"], places=6)

    def test_timeline_has_one_snapshot_per_time(self):
        timeline = self.predictor.timeline(self.views)
        self.assertEqual(len(timeline), len(self.views))
        self.assertEqual(list(timeline[0]["probabilities"]), ["A"])
        self.assertEqual(set(timeline[-1]["probabilities"]), {"A", "B", "C"})
        final = {c["item_id"]: c["probability"] for c in self.predictor.predict(self.views)["candidates"]}
        for item, p in timeline[-1]["probabilities"].items():
            self.assertAlmostEqual(p, final[item], places=9)

    def test_input_order_and_datetime_strings(self):
        shuffled = list(reversed(self.views))
        as_text = [
            (f"2026-09-30T10:{t // MINUTE:02d}:00Z", item) for t, item in self.views
        ]
        base = self.predictor.predict(self.views)["candidates"]
        for other in (self.predictor.predict(shuffled), self.predictor.predict(as_text)):
            for x, y in zip(base, other["candidates"]):
                self.assertEqual(x["item_id"], y["item_id"])
                self.assertAlmostEqual(x["probability"], y["probability"], places=9)

    def test_purchased_item_is_excluded(self):
        result = self.predictor.predict(self.views, purchases=[(4 * MINUTE, "C")])
        self.assertEqual(result["purchased"], ["C"])
        self.assertNotIn("C", {c["item_id"] for c in result["candidates"]})

    def test_all_items_purchased(self):
        result = self.predictor.predict([(0, "A")], purchases=[(0, "A")])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["purchased"], ["A"])

    def test_first_view_probability_is_same_for_any_item(self):
        a = self.predictor.predict([(0, "A")])["candidates"][0]["probability"]
        b = self.predictor.predict([(10 * MINUTE, 12345)])["candidates"][0]["probability"]
        self.assertAlmostEqual(a, b, places=9)

    def test_empty_log(self):
        with self.assertRaises(ValueError):
            self.predictor.predict([])


if __name__ == "__main__":
    unittest.main()
