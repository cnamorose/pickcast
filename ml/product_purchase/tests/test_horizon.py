"""horizon.py(앞으로 10분 안에 살 확률)를 손으로 만든 비율과 Git에 있는 v3 비율로 확인한다."""
import unittest

import numpy as np

from horizon import (
    ACTIVE_MINUTES,
    RATES_FILE,
    RateCounter,
    elapsed_bin,
    load_rates,
    within_horizon,
)
from release import list_versions, release_dir


# 구간: [0, 10), [10, 60), [60, 24시간)
EDGES = [0, 10, 60, ACTIVE_MINUTES]
RATES = {
    "edges_minutes": EDGES,
    "carted": [0.5, 0.1, 0.01],
    "not_carted": [0.2, 0.05, 0.0],
}


class WithinHorizonTest(unittest.TestCase):
    def test_zero_probability_stays_zero(self):
        self.assertEqual(float(within_horizon(0.0, 0, True, RATES)), 0.0)

    def test_uses_group_and_elapsed_rate(self):
        self.assertAlmostEqual(float(within_horizon(0.4, 5, True, RATES)), 0.2)
        self.assertAlmostEqual(float(within_horizon(0.4, 5, False, RATES)), 0.08)
        self.assertAlmostEqual(float(within_horizon(0.4, 30, True, RATES)), 0.04)

    def test_inactive_customer_is_zero(self):
        self.assertEqual(float(within_horizon(0.9, ACTIVE_MINUTES, True, RATES)), 0.0)
        self.assertEqual(float(within_horizon(0.9, -1, True, RATES)), 0.0)

    def test_capped_at_one(self):
        rates = {**RATES, "carted": [5.0, 0.1, 0.01]}
        self.assertEqual(float(within_horizon(0.9, 0, True, rates)), 1.0)

    def test_vectorized(self):
        q = within_horizon([0.4, 0.4], [5, 30], [True, False], RATES)
        np.testing.assert_allclose(q, [0.2, 0.02])


class RateCounterTest(unittest.TestCase):
    def test_bins(self):
        np.testing.assert_array_equal(elapsed_bin([0, 9.9, 10, 59, 60, 5000], EDGES), [0, 0, 1, 1, 2, 2])

    def test_rate_is_sales_over_probability_sum(self):
        counter = RateCounter(EDGES)
        # 담은 상품, 0~10분 구간: 확률 합 1.0, 판매 1 → 1.0 / 30분 구간: 확률 합 0.5, 판매 0
        counter.add([0.5, 0.5, 0.5], [1, 2, 30], [True, True, True], [True, False, False])
        # 담지 않은 상품: 확률 합 0.4, 판매 1 → 2.5
        counter.add([0.2, 0.2], [3, 4], [False, False], [False, True])
        rates = counter.rates()
        self.assertEqual(rates["carted"], [1.0, 0.0, 0.0])
        self.assertEqual(rates["not_carted"], [2.5, 0.0, 0.0])
        self.assertEqual(rates["carted_sales"], 1)

    def test_group_without_sales_is_rejected(self):
        counter = RateCounter(EDGES)
        counter.add([0.5], [1], [True], [True])
        with self.assertRaises(ValueError):
            counter.rates()

    def test_fitted_rates_reproduce_sales(self):
        # 비율을 만든 쌍에 다시 적용하면 구간별 예상 판매 합이 실제 판매 수와 같다.
        rng = np.random.default_rng(0)
        p = rng.uniform(0, 0.3, 500)
        elapsed = rng.uniform(0, 300, 500)
        carted = rng.random(500) < 0.4
        sold = rng.random(500) < p * 0.3
        counter = RateCounter(EDGES)
        counter.add(p, elapsed, carted, sold)
        q = within_horizon(p, elapsed, carted, counter.rates())
        self.assertAlmostEqual(float(q.sum()), float(sold.sum()), places=3)


def versions_with_rates():
    return [
        v["version"] for v in list_versions()
        if v["problem"] is None and (release_dir(v["version"]) / RATES_FILE).exists()
    ]


@unittest.skipUnless(versions_with_rates(), "10분 판매 비율이 있는 버전이 없습니다")
class StoredRatesTest(unittest.TestCase):
    def test_carted_sells_faster_right_after(self):
        rates = load_rates(release_dir(versions_with_rates()[-1]))
        bins = len(rates["edges_minutes"]) - 1
        self.assertEqual(len(rates["carted"]), bins)
        self.assertEqual(len(rates["not_carted"]), bins)
        self.assertTrue(all(r >= 0 for r in rates["carted"] + rates["not_carted"]))
        # 담은 상품은 마지막 행동 직후 10분 안에 더 잘 팔린다
        self.assertGreater(rates["carted"][0], rates["not_carted"][0])


if __name__ == "__main__":
    unittest.main()
