"""dashboard.py의 집계를 손으로 계산할 수 있는 작은 입력으로 확인한다."""
import math
import unittest

from dashboard import (
    STAGES,
    compare_pairs,
    count_stages,
    forecast_sales,
    purchase_count_distribution,
)


def binomial(n, p):
    return [math.comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(n + 1)]


class PurchaseCountDistributionTest(unittest.TestCase):
    def test_empty_is_zero_sales(self):
        self.assertEqual(purchase_count_distribution([]), [1.0])

    def test_two_customers_by_hand(self):
        # 0명: 0.9×0.8, 1명: 0.1×0.8 + 0.9×0.2, 2명: 0.1×0.2
        distribution = purchase_count_distribution([0.1, 0.2])
        for got, want in zip(distribution, [0.72, 0.26, 0.02]):
            self.assertAlmostEqual(got, want)

    def test_equal_probabilities_match_binomial(self):
        distribution = purchase_count_distribution([0.3] * 6)
        for got, want in zip(distribution, binomial(6, 0.3)):
            self.assertAlmostEqual(got, want)

    def test_sums_to_one(self):
        distribution = purchase_count_distribution([0.01, 0.5, 0.33, 0.9, 0.07])
        self.assertAlmostEqual(sum(distribution), 1.0)


class ForecastSalesTest(unittest.TestCase):
    def test_fields(self):
        [forecast] = forecast_sales({"A": [0.1, 0.2]})
        self.assertEqual(forecast["item_id"], "A")
        self.assertEqual(forecast["viewers"], 2)
        self.assertAlmostEqual(forecast["expected"], 0.3)
        self.assertAlmostEqual(forecast["at_least_one"], 0.28)

    def test_interval_by_hand(self):
        # 분포 [0.72, 0.26, 0.02]: 누적 0.72, 0.98, 1.0 → 5%는 0명, 95%는 1명
        [forecast] = forecast_sales({"A": [0.1, 0.2]})
        self.assertEqual((forecast["low"], forecast["high"]), (0, 1))

    def test_interval_contains_expected(self):
        probabilities = [0.02, 0.05, 0.3, 0.6, 0.45, 0.1, 0.8, 0.25]
        [forecast] = forecast_sales({"A": probabilities})
        self.assertLessEqual(forecast["low"], forecast["expected"])
        self.assertGreaterEqual(forecast["high"], forecast["expected"])

    def test_wider_interval_is_not_narrower(self):
        probabilities = [0.3] * 20
        [narrow] = forecast_sales({"A": probabilities}, interval=0.5)
        [wide] = forecast_sales({"A": probabilities}, interval=0.9)
        self.assertLessEqual(wide["low"], narrow["low"])
        self.assertGreaterEqual(wide["high"], narrow["high"])

    def test_small_probabilities_round_to_zero_range(self):
        # 실제 서비스처럼 확률이 0.5~5%면 예상 구매 수는 작고 범위는 0~0 또는 0~1
        [forecast] = forecast_sales({"A": [0.01, 0.02, 0.03]})
        self.assertLess(forecast["expected"], 0.1)
        self.assertEqual(forecast["low"], 0)
        self.assertLessEqual(forecast["high"], 1)

    def test_sorted_by_expected(self):
        forecasts = forecast_sales({"A": [0.1], "B": [0.3, 0.2], "C": [0.05]})
        self.assertEqual([f["item_id"] for f in forecasts], ["B", "A", "C"])


class CountStagesTest(unittest.TestCase):
    def test_counts_with_zero_for_missing(self):
        counts = count_stages(["browsing", "comparing", "browsing"])
        self.assertEqual(counts, {"browsing": 2, "comparing": 1, "decided": 0, "leaving": 0})

    def test_empty(self):
        self.assertEqual(count_stages([]), {stage: 0 for stage in STAGES})


class ComparePairsTest(unittest.TestCase):
    def test_only_comparing_sessions(self):
        results = [
            {"stage": "comparing", "items": ["A", "B"]},
            {"stage": "decided", "items": ["A"]},
            {"stage": "browsing", "items": []},
        ]
        self.assertEqual(compare_pairs(results), [{"items": ["A", "B"], "sessions": 1}])

    def test_order_does_not_matter(self):
        results = [
            {"stage": "comparing", "items": ["A", "B"]},
            {"stage": "comparing", "items": ["B", "A"]},
        ]
        self.assertEqual(compare_pairs(results), [{"items": ["A", "B"], "sessions": 2}])

    def test_three_items_make_three_pairs(self):
        results = [{"stage": "comparing", "items": ["C", "A", "B"]}]
        pairs = [p["items"] for p in compare_pairs(results)]
        self.assertEqual(pairs, [["A", "B"], ["A", "C"], ["B", "C"]])

    def test_sorted_by_sessions_and_limit(self):
        results = [
            {"stage": "comparing", "items": ["A", "C"]},
            {"stage": "comparing", "items": ["B", "D"]},
            {"stage": "comparing", "items": ["B", "D"]},
        ]
        self.assertEqual(
            compare_pairs(results, limit=1), [{"items": ["B", "D"], "sessions": 2}]
        )


if __name__ == "__main__":
    unittest.main()
