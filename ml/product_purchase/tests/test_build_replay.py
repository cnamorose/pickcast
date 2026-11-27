"""build_replay.py의 계산(쇼핑 중 고객 수, 1분 예상 판매, 구매 확인)을 손으로 만든 기록으로 확인한다."""
import unittest

import numpy as np
import pandas as pd

from build_replay import active_counts, minute_forecasts, purchase_checks
from horizon import ACTIVE_MINUTES
from horizon_rows import MINUTE, NEVER

START = 1_000 * MINUTE
A, B, C = 11, 12, 13


class ActiveCountsTest(unittest.TestCase):
    def test_overlapping_and_separate_visits(self):
        users = [1, 1, 2, 3]
        times = [START, START + 10 * MINUTE, START + 50 * MINUTE, START - 5 * MINUTE]
        counts = active_counts(users, times, START, 90, window_minutes=30)
        expected = np.zeros(90, dtype=int)
        expected[0:40] += 1   # 고객 1: 0분, 10분 행동 → 0~39분 (겹치는 부분은 한 번만)
        expected[50:80] += 1  # 고객 2: 50분 행동
        expected[0:25] += 1   # 고객 3: 시작 5분 전 행동 → 24분까지
        np.testing.assert_array_equal(counts, expected)

    def test_action_inside_a_minute_counts_from_next_minute(self):
        counts = active_counts([1], [START + 30_000], START, 3, window_minutes=1)
        np.testing.assert_array_equal(counts, [0, 1, 0])


class MinuteForecastsTest(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "visitorid": [1, 1],
            "cutoff_timestamp": [START, START],
            "itemid": [A, B],
            "cart_count": [1, 0],
        })
        self.rates = {"edges_minutes": [0, ACTIVE_MINUTES], "carted": [0.5], "not_carted": [0.1]}

    def test_totals_and_top_items(self):
        p = np.array([0.2, 0.4])
        bought = np.full(2, NEVER, dtype=np.int64)
        totals, top = minute_forecasts(self.frame, p, bought, self.rates, START, 3)
        np.testing.assert_allclose(totals, [0.14, 0.14, 0.14])
        self.assertEqual(top[0][0], [A, 0.1, 0.1, 1])
        self.assertEqual(top[0][1], [B, 0.04, 0.04, 1])

    def test_bought_item_leaves_forecast(self):
        p = np.array([0.2, 0.4])
        bought = np.array([START + 90_000, NEVER], dtype=np.int64)  # A가 1분 30초에 팔림
        totals, top = minute_forecasts(self.frame, p, bought, self.rates, START, 3)
        np.testing.assert_allclose(totals, [0.14, 0.14, 0.04])
        self.assertEqual([item[0] for item in top[2]], [B])


class PurchaseChecksTest(unittest.TestCase):
    def setUp(self):
        t0, t1 = START, START + 5 * MINUTE
        self.t2 = START + 9 * MINUTE
        self.frame = pd.DataFrame({
            "visitorid": [1, 1, 1, 1],
            "cutoff_timestamp": [t0, t0, t1, t1],
            "itemid": [A, B, A, B],
            "touched_now": [1, 1, 1, 0],
        })
        self.p = np.array([0.1, 0.3, 0.4, 0.2])

    def test_checkout_touch_uses_previous_point(self):
        # A는 t1에 방금 봤으므로 t0 예측: 확률 0.1, B(0.3) 다음 2위
        result = purchase_checks(self.frame, self.p, [(1, A, self.t2)])[0]
        self.assertEqual(result, (0.1, 2, 2, 9.0))

    def test_latest_point_when_not_just_touched(self):
        result = purchase_checks(self.frame, self.p, [(1, B, self.t2)])[0]
        self.assertEqual(result, (0.2, 2, 2, 4.0))

    def test_unknown_item_or_user(self):
        results = purchase_checks(self.frame, self.p, [(1, C, self.t2), (2, A, self.t2)])
        self.assertEqual(results, [None, None])


if __name__ == "__main__":
    unittest.main()
