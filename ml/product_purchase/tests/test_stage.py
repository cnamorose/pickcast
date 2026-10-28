"""stage.py의 단계 판단 규칙을 확인한다.

규칙 테스트는 손으로 만든 timeline을, 시나리오 테스트는 Git에 포함된 확정 모델을 쓴다.
"""
import unittest

from predict import PurchasePredictor
from stage import STAGE_THRESHOLDS, judge_stage


BASE = 0.01
SECOND = 1000


def snapshot(viewed, **lifts):
    """조회한 상품과 상품별 lift(기준 확률 대비 배수)로 timeline 한 칸을 만든다."""
    return {
        "timestamp": 0,
        "viewed": [viewed],
        "probabilities": {item: lift * BASE for item, lift in lifts.items()},
    }


class JudgeStageRuleTest(unittest.TestCase):
    def test_too_few_views_is_browsing(self):
        timeline = [snapshot("A", A=1), snapshot("A", A=5)]
        self.assertEqual(judge_stage(timeline, BASE)["stage"], "browsing")

    def test_empty_timeline_is_browsing(self):
        self.assertEqual(judge_stage([], BASE)["stage"], "browsing")

    def test_decided(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("A", A=4, B=1.5),
        ]
        result = judge_stage(timeline, BASE)
        self.assertEqual(result["stage"], "decided")
        self.assertEqual(result["items"], ["A"])

    def test_close_top_two_is_comparing(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("C", A=2.5, B=2.2, C=2.1),
        ]
        result = judge_stage(timeline, BASE)
        self.assertEqual(result["stage"], "comparing")
        self.assertEqual(result["items"], ["A", "B", "C"])

    def test_comparing_items_exclude_low_lift(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("C", A=2.5, B=2.2, C=1.2),
        ]
        self.assertEqual(judge_stage(timeline, BASE)["items"], ["A", "B"])

    def test_no_standout_is_browsing(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=0.7, B=1.1),
            snapshot("C", A=1.2, B=1.0, C=1.4),
        ]
        self.assertEqual(judge_stage(timeline, BASE)["stage"], "browsing")

    def test_leaving_when_share_drops_without_revisit(self):
        timeline = [
            snapshot("A", A=4),
            snapshot("B", A=4, B=2),
            snapshot("C", A=4, B=2, C=2),
            snapshot("D", A=4, B=2, C=2, D=2),
        ]
        result = judge_stage(timeline, BASE)
        self.assertEqual(result["stage"], "leaving")
        self.assertEqual(result["items"], ["A"])

    def test_leaving_checked_before_decided(self):
        # A를 안 보는 동안 A의 lift가 올라 decided 조건도 만족하지만 leaving이 우선
        timeline = [
            snapshot("A", A=4),
            snapshot("B", A=4, B=1),
            snapshot("C", A=4, B=1, C=1),
            snapshot("D", A=8, B=1, C=1, D=1),
        ]
        self.assertEqual(judge_stage(timeline, BASE)["stage"], "leaving")

    def test_recent_revisit_is_not_leaving(self):
        timeline = [
            snapshot("A", A=4),
            snapshot("B", A=4, B=2),
            snapshot("C", A=4, B=2, C=2),
            snapshot("A", A=5, B=2, C=2),
        ]
        self.assertNotEqual(judge_stage(timeline, BASE)["stage"], "leaving")

    def test_low_lift_item_is_not_leaving(self):
        timeline = [
            snapshot("A", A=2),
            snapshot("B", A=2, B=1),
            snapshot("C", A=2, B=1, C=1),
            snapshot("D", A=2, B=1, C=1, D=1),
        ]
        self.assertNotEqual(judge_stage(timeline, BASE)["stage"], "leaving")

    def test_thresholds_can_be_overridden(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("A", A=4, B=1.5),
        ]
        strict = {**STAGE_THRESHOLDS, "decided_lift": 10.0}
        self.assertNotEqual(judge_stage(timeline, BASE, strict)["stage"], "decided")


class JudgeStageScenarioTest(unittest.TestCase):
    """실제 모델 확률로 대표적인 쇼핑 흐름이 의도한 단계가 되는지 확인한다."""

    @classmethod
    def setUpClass(cls):
        cls.predictor = PurchasePredictor()

    def judge(self, items, gap=30 * SECOND):
        views = [(k * gap, item) for k, item in enumerate(items)]
        timeline = self.predictor.timeline(views)
        return judge_stage(timeline, self.predictor.base_probability)

    def test_base_probability(self):
        # 기획서: 처음 한 번 보면 모든 상품이 약 0.55%
        self.assertAlmostEqual(self.predictor.base_probability, 0.0055, delta=0.001)

    def test_all_different_items_is_browsing(self):
        self.assertEqual(self.judge("ABCDEF")["stage"], "browsing")

    def test_repeated_item_is_decided(self):
        result = self.judge("ABAAA")
        self.assertEqual(result["stage"], "decided")
        self.assertEqual(result["items"], ["A"])

    def test_alternating_items_is_comparing(self):
        result = self.judge("ABABAB")
        self.assertEqual(result["stage"], "comparing")
        self.assertEqual(set(result["items"]), {"A", "B"})

    def test_moving_away_is_leaving(self):
        result = self.judge("AAABCDEF", gap=20 * SECOND)
        self.assertEqual(result["stage"], "leaving")
        self.assertEqual(result["items"], ["A"])


if __name__ == "__main__":
    unittest.main()
