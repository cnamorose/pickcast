"""결과 화면 예측에서 결제 직전 조회를 빼는 규칙(views_before_decision)을 확인한다."""
import unittest

from backend.app.sessions import views_before_decision


def views(*items):
    """(timestamp, item_id) 목록. 시각은 순서만 맞으면 된다."""
    return [(i * 1000, item) for i, item in enumerate(items)]


class ViewsBeforeDecisionTest(unittest.TestCase):
    def test_drops_only_last_view_of_purchased_item(self):
        # 같은 상품을 연달아 다시 본 조회는 남기고, 결제하러 들어간 마지막 1개만 뺀다
        result = views_before_decision(views("B", "C", "A", "A", "A"), "A")
        self.assertEqual([item for _, item in result], ["B", "C", "A", "A"])

    def test_keeps_earlier_views_of_purchased_item(self):
        result = views_before_decision(views("A", "B", "A"), "A")
        self.assertEqual([item for _, item in result], ["A", "B"])

    def test_only_purchased_item_viewed(self):
        # 산 상품만 여러 번 봤으면 마지막 1개만 빠지고 나머지로 예측한다
        result = views_before_decision(views("A", "A", "A"), "A")
        self.assertEqual([item for _, item in result], ["A", "A"])

    def test_single_view_leaves_nothing(self):
        self.assertEqual(views_before_decision(views("A"), "A"), [])

    def test_last_view_is_other_item(self):
        # 마지막 조회가 산 상품이 아니면 아무것도 빼지 않는다
        original = views("A", "B")
        self.assertEqual(views_before_decision(original, "A"), original)


if __name__ == "__main__":
    unittest.main()
