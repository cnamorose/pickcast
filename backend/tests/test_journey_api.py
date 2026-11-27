"""journey_api.py(손님 한 명 따라가기)의 대시보드 계산과 구매 결과를 확인한다."""
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app.journey_api import (
    dashboard_at,
    get_journey,
    get_journeys,
    journeys,
    model,
    purchase_outcomes,
)

A, B, C = 388536, 210002, 217794  # 저장소 손님 기록에 있는 상품 번호 (상품 통계가 붙는다)


def step(*ranked):
    """손으로 만든 대시보드: ranked 순서대로 1, 2, 3위."""
    return {"dashboard": {"candidates": [
        {"item_id": item, "rank": r, "probability": 0.1 / r} for r, item in enumerate(ranked, start=1)
    ]}}


class PurchaseOutcomesTest(unittest.TestCase):
    def test_lead_time_and_checkout_rule(self):
        events = [[0, "view", B], [10, "view", A], [30, "addtocart", A], [90, "transaction", A]]
        steps = [step(B), step(B, A), step(A, B), step(A, B)]
        outcome = purchase_outcomes(events, steps)[0]
        self.assertEqual(outcome["rank_before"], 1)
        # 바로 앞 행동(A 담기)을 빼면 A를 본 직후의 순위(2위)
        self.assertEqual(outcome["rank_excluding_checkout"], 2)
        # 담은 30초부터 구매(90초)까지 계속 1위
        self.assertEqual(outcome["top1_seconds_before"], 60)

    def test_same_item_counts_once(self):
        events = [[0, "view", A], [5, "transaction", A], [6, "transaction", A]]
        steps = [step(A), step(), step()]
        outcomes = purchase_outcomes(events, steps)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["top1_seconds_before"], 5)

    def test_not_top1(self):
        events = [[0, "view", A], [10, "view", B], [20, "transaction", A]]
        outcome = purchase_outcomes(events, [step(A), step(B, A), step(B)])[0]
        self.assertEqual(outcome["rank_before"], 2)
        self.assertIsNone(outcome["top1_seconds_before"])


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.predictor, self.rates = model()
        self.events = [[0, "view", A], [20, "view", B], [40, "addtocart", A], [60, "transaction", A], [70, "view", C]]

    def test_cart_puts_item_first(self):
        board = dashboard_at(self.events, 40, self.predictor, self.rates)
        first = board["candidates"][0]
        self.assertEqual(first["item_id"], A)
        self.assertTrue(first["carted"])
        self.assertEqual([c["rank"] for c in board["candidates"]], list(range(1, len(board["candidates"]) + 1)))
        self.assertEqual(len(first["reasons"]), 3)

    def test_bought_item_leaves_right_after_purchase(self):
        board = dashboard_at(self.events, 60, self.predictor, self.rates)
        self.assertNotIn(A, [c["item_id"] for c in board["candidates"]])
        self.assertEqual(board["purchased"], [A])
        self.assertEqual(board["candidates"][0]["rank"], 1)


class JourneyApiTest(unittest.TestCase):
    def test_missing_file_is_404(self):
        directory = Path(tempfile.mkdtemp())
        try:
            with self.assertRaises(HTTPException) as caught:
                journeys(directory / "none.json")
            self.assertEqual(caught.exception.status_code, 404)
        finally:
            shutil.rmtree(directory)

    def test_unknown_customer_is_404(self):
        with self.assertRaises(HTTPException) as caught:
            get_journey(999)
        self.assertEqual(caught.exception.status_code, 404)

    def test_repository_journeys(self):
        customers = get_journeys()["customers"]
        self.assertEqual(len(customers), 9)
        self.assertEqual({c["type"] for c in customers}, {"compare_buy", "cart_leave", "quick_buy"})
        for summary in customers:
            journey = get_journey(summary["id"])
            self.assertEqual(journey["version"], "product_purchase_v3")
            steps = journey["steps"]
            for current, following in zip(steps, steps[1:]):
                self.assertAlmostEqual(current["dwell_seconds"], following["second"] - current["second"], places=1)
            self.assertIsNone(steps[-1]["dwell_seconds"])
            if summary["type"] == "cart_leave":
                self.assertEqual(summary["bought"], [])
            else:
                self.assertTrue(summary["bought"])


if __name__ == "__main__":
    unittest.main()
