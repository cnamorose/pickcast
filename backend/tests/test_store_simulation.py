"""store_simulation.py(가게 전체 대시보드의 가정 재고·알림)를 손으로 만든 재생 데이터로 확인한다."""
import unittest

from backend.app.store_simulation import (
    MAX_STOCK,
    MIN_STOCK,
    REFILL_CHANCE,
    REFILL_STOCK,
    initial_stock,
    stock_status,
    window_store,
)


def stock_of(target):
    """가정 재고가 target인 상품 번호를 하나 찾는다."""
    return next(item for item in range(1, 10_000) if initial_stock(item) == target)


class StockTest(unittest.TestCase):
    def test_initial_stock_is_fixed_and_in_range(self):
        values = [initial_stock(item) for item in range(1, 2000)]
        self.assertEqual(min(values), MIN_STOCK)
        self.assertEqual(max(values), MAX_STOCK)
        self.assertEqual(initial_stock(461686), initial_stock(461686))

    def test_status(self):
        self.assertEqual(stock_status(0, 0.0), "soldout")
        self.assertEqual(stock_status(REFILL_STOCK, REFILL_CHANCE), "refill")
        self.assertEqual(stock_status(REFILL_STOCK, REFILL_CHANCE - 0.01), "ok")
        self.assertEqual(stock_status(REFILL_STOCK + 1, 0.9), "ok")


class WindowStoreTest(unittest.TestCase):
    def setUp(self):
        self.item = stock_of(2)
        other = stock_of(5)
        # 하루 5분, 시간 창은 1~3분. 상품은 1분 30초와 2분 30초에 팔려 재고 2 → 1 → 0
        self.day = {
            "snapshots": {
                "shoppers": [1, 2, 3, 4, 5],
                "carting": [0, 1, 1, 0, 0],
                "expected_next_10m": [0.1, 0.2, 0.3, 0.4, 0.5],
                "top_item_columns": ["item", "expected", "at_least_one", "customers"],
                "top_items": [[[self.item, 0.2, 0.2, 3], [other, 0.05, 0.05, 1]]] * 5,
            },
            "actual_known_next_10m": [0, 1, 1, 0, 0],
            "purchases": {
                "columns": ["second", "customer", "item", "probability", "rank", "candidates", "minutes_before"],
                "rows": [
                    [30.0, 1, self.item, 0.2, 1, 2, 1.0],   # 시간 창 전
                    [90.0, 2, self.item, 0.3, 1, 2, 1.0],
                    [150.0, 3, self.item, None, None, None, None],
                ],
            },
        }

    def test_slices_window_and_tracks_stock(self):
        store = window_store(self.day, start_minute=1, minutes=3)
        self.assertEqual(store["shoppers"], [2, 3, 4])
        self.assertEqual(store["actual_known_next_10m"], [1, 1, 0])
        self.assertEqual([s["second"] for s in store["sales"]], [30.0, 90.0])  # 창 시작(60초)부터
        first = [row[0] for row in store["top_items"]]
        # 1분(창 0분): 재고 2, 확률 20% → 채우세요 / 2분: 1개 팔려 1 / 3분: 0 → 품절
        self.assertEqual([(r[4], r[5]) for r in first], [(2, "refill"), (1, "refill"), (0, "soldout")])
        self.assertEqual([row[1][5] for row in store["top_items"]], ["ok", "ok", "ok"])
        self.assertEqual(store["initial_stock"], {str(self.item): 2})


if __name__ == "__main__":
    unittest.main()
