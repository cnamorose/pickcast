"""insights.py의 규칙마다 걸리는 경우와 안 걸리는 경우를 확인한다."""
import unittest

from backend.app.insights import INSIGHT_THRESHOLDS, dashboard_insights


def product(item, viewers=0, high=0, purchased=0, stock=10):
    return {"item_id": item, "viewers": viewers, "high": high, "purchased": purchased, "stock": stock}


def types(insights):
    return [insight["type"] for insight in insights]


# 재고 규칙만 보려면 관심 대비 의도 약함 규칙에 걸리지 않을 만큼만 본 고객을 둔다
FEW = INSIGHT_THRESHOLDS["weak_intent_viewers"] - 1


class StockInsightTest(unittest.TestCase):
    def test_sold_out_with_viewers(self):
        insights = dashboard_insights(10, [product("A", viewers=2, purchased=1, stock=1)], [], [])
        self.assertEqual(types(insights), ["low_stock"])
        self.assertIn("모두 팔렸", insights[0]["message"])

    def test_low_remaining_with_viewers(self):
        insights = dashboard_insights(10, [product("A", viewers=FEW, purchased=4, stock=5)], [], [])
        self.assertEqual(types(insights), ["low_stock"])
        self.assertIn("남은 재고 1개", insights[0]["message"])

    def test_forecast_upper_bound_raises_threshold(self):
        # 남은 재고 3개여도 예상 범위 상한이 3이면 부족할 수 있음
        insights = dashboard_insights(10, [product("A", viewers=FEW, high=3, stock=3)], [], [])
        self.assertEqual(types(insights), ["low_stock"])

    def test_no_viewers_is_skipped(self):
        insights = dashboard_insights(10, [product("A", viewers=0, purchased=1, stock=1)], [], [])
        self.assertEqual(insights, [])

    def test_enough_stock_is_skipped(self):
        insights = dashboard_insights(10, [product("A", viewers=FEW, stock=5)], [], [])
        self.assertEqual(insights, [])

    def test_unknown_stock_is_skipped(self):
        insights = dashboard_insights(10, [product("A", viewers=FEW, stock=None)], [], [])
        self.assertEqual(insights, [])

    def test_sold_out_comes_before_low_remaining(self):
        products = [
            product("A", viewers=2, purchased=4, stock=5),
            product("B", viewers=1, purchased=2, stock=2),
        ]
        self.assertEqual([i["items"][0] for i in dashboard_insights(10, products, [], [])], ["B", "A"])


class BehaviorInsightTest(unittest.TestCase):
    def test_comparing_pair(self):
        pairs = [{"items": ["A", "B"], "sessions": 2}, {"items": ["C", "D"], "sessions": 1}]
        insights = dashboard_insights(10, [], [], pairs)
        self.assertEqual(types(insights), ["comparing_pair"])
        self.assertEqual(insights[0]["items"], ["A", "B"])

    def test_weak_intent(self):
        products = [product("A", viewers=3), product("B", viewers=2)]
        insights = dashboard_insights(10, products, [{"stage": "browsing", "items": []}], [])
        self.assertEqual([(i["type"], i["items"]) for i in insights], [("weak_intent", ["A"])])

    def test_decided_customer_removes_weak_intent(self):
        products = [product("A", viewers=3)]
        stages = [{"stage": "decided", "items": ["A"]}]
        self.assertEqual(dashboard_insights(10, products, stages, []), [])

    def test_leaving(self):
        stages = [
            {"stage": "leaving", "items": ["A"]},
            {"stage": "leaving", "items": ["A"]},
            {"stage": "leaving", "items": ["B"]},
        ]
        insights = dashboard_insights(10, [], stages, [])
        self.assertEqual([(i["type"], i["items"]) for i in insights], [("leaving", ["A"])])


class OrderAndGuardTest(unittest.TestCase):
    def setUp(self):
        self.products = [
            product("S", viewers=1, purchased=1, stock=1),
            product("W", viewers=4),
        ]
        self.stages = [{"stage": "leaving", "items": ["L"]}] * 2
        self.pairs = [{"items": ["A", "B"], "sessions": 3}]

    def test_order(self):
        insights = dashboard_insights(10, self.products, self.stages, self.pairs)
        self.assertEqual(types(insights), ["low_stock", "comparing_pair", "weak_intent", "leaving"])

    def test_limit(self):
        insights = dashboard_insights(10, self.products, self.stages, self.pairs, limit=2)
        self.assertEqual(types(insights), ["low_stock", "comparing_pair"])

    def test_one_type_does_not_take_every_slot(self):
        products = [product(f"S{k}", viewers=1, purchased=1, stock=1) for k in range(5)]
        insights = dashboard_insights(10, products, self.stages, self.pairs, per_type=2)
        self.assertEqual(types(insights), ["low_stock", "low_stock", "comparing_pair", "leaving"])

    def test_too_few_sessions_keeps_only_stock(self):
        few = INSIGHT_THRESHOLDS["min_active_sessions"] - 1
        insights = dashboard_insights(few, self.products, self.stages, self.pairs)
        self.assertEqual(types(insights), ["too_few_sessions", "low_stock"])

    def test_each_insight_has_message(self):
        for insight in dashboard_insights(10, self.products, self.stages, self.pairs):
            self.assertTrue(insight["message"])
            self.assertIsInstance(insight["items"], list)


if __name__ == "__main__":
    unittest.main()
