"""stage.py의 단계 판단 규칙을 확인한다.

규칙 테스트는 손으로 만든 timeline을, 시나리오 테스트는 Git에 포함된 모든 모델 버전을 쓴다.
모델 버전을 바꿔도(release.py use) 단계 기준값이 그대로 통하는지 확인하기 위해서다.
"""
import unittest

from predict import PurchasePredictor
from release import list_versions, release_dir
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
            snapshot("C", A=1, B=1, C=1),
            snapshot("A", A=2, B=1, C=1),
            snapshot("B", A=2, B=2, C=1),
            snapshot("C", A=2.5, B=2.2, C=2.1),
        ]
        result = judge_stage(timeline, BASE)
        self.assertEqual(result["stage"], "comparing")
        self.assertEqual(result["items"], ["A", "B", "C"])

    def test_comparing_items_exclude_low_lift(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("C", A=1, B=1, C=1),
            snapshot("A", A=2, B=1, C=1),
            snapshot("B", A=2, B=2, C=1),
            snapshot("C", A=2.5, B=2.2, C=1.2),
        ]
        self.assertEqual(judge_stage(timeline, BASE)["items"], ["A", "B"])

    def test_single_view_item_is_not_compared(self):
        # 방금 한 번 연 B는 확률이 높아도 고민 대상이 아님 (A A B)
        timeline = [
            snapshot("A", A=1),
            snapshot("A", A=2.5),
            snapshot("B", A=2.6, B=2.2),
        ]
        self.assertNotEqual(judge_stage(timeline, BASE)["stage"], "comparing")

    def test_decided_requires_repeat_view(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("C", A=1, B=1, C=4),
        ]
        self.assertNotEqual(judge_stage(timeline, BASE)["stage"], "decided")

    def test_no_standout_is_browsing(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=0.7, B=1.1),
            snapshot("C", A=1.2, B=1.0, C=1.4),
        ]
        self.assertEqual(judge_stage(timeline, BASE)["stage"], "browsing")

    def test_leaving_when_share_drops_without_revisit(self):
        timeline = [
            snapshot("A", A=1),
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
            snapshot("A", A=1),
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
        low = STAGE_THRESHOLDS["leaving_lift"] * 0.8
        timeline = [
            snapshot("A", A=low),
            snapshot("B", A=low, B=1),
            snapshot("C", A=low, B=1, C=1),
            snapshot("D", A=low, B=1, C=1, D=1),
        ]
        self.assertNotEqual(judge_stage(timeline, BASE)["stage"], "leaving")

    def test_low_share_top_item_is_not_decided(self):
        # lift와 ratio는 충분하지만 후보가 많아 1위 비중이 낮으면 살 마음 먹음이 아님
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("C", A=1, B=1, C=1),
            snapshot("D", A=1, B=1, C=1, D=1),
            snapshot("D", A=1, B=1, C=1, D=2.5),
        ]
        self.assertNotEqual(judge_stage(timeline, BASE)["stage"], "decided")

    def test_thresholds_can_be_overridden(self):
        timeline = [
            snapshot("A", A=1),
            snapshot("B", A=1, B=1),
            snapshot("A", A=4, B=1.5),
        ]
        strict = {**STAGE_THRESHOLDS, "decided_lift": 10.0}
        self.assertNotEqual(judge_stage(timeline, BASE, strict)["stage"], "decided")


class JudgeStageScenarioTest(unittest.TestCase):
    """실제 모델 확률로 대표적인 쇼핑 흐름이 의도한 단계가 되는지, 모든 모델 버전에서 확인한다."""

    @classmethod
    def setUpClass(cls):
        cls.predictors = {
            v["version"]: PurchasePredictor(release_dir(v["version"]))
            for v in list_versions()
            if v["problem"] is None
        }

    def judge(self, predictor, items, gap=30 * SECOND):
        views = [(k * gap, item) for k, item in enumerate(items)]
        return judge_stage(predictor.timeline(views), predictor.base_probability)

    def each_version(self):
        for version, predictor in self.predictors.items():
            with self.subTest(version=version):
                yield predictor

    def test_base_probability(self):
        # 기획서: 처음 한 번 보면 모든 상품이 약 0.55%
        for predictor in self.each_version():
            self.assertAlmostEqual(predictor.base_probability, 0.0055, delta=0.001)

    def test_all_different_items_is_browsing(self):
        for predictor in self.each_version():
            self.assertEqual(self.judge(predictor, "ABCDEF")["stage"], "browsing")

    def test_repeated_item_is_decided(self):
        for predictor in self.each_version():
            result = self.judge(predictor, "ABAAA")
            self.assertEqual(result["stage"], "decided")
            self.assertEqual(result["items"], ["A"])

    def test_alternating_items_is_comparing(self):
        for predictor in self.each_version():
            result = self.judge(predictor, "ABABAB")
            self.assertEqual(result["stage"], "comparing")
            self.assertEqual(set(result["items"]), {"A", "B"})

    def test_moving_away_is_leaving(self):
        for predictor in self.each_version():
            result = self.judge(predictor, "AAABCDEF", gap=20 * SECOND)
            self.assertEqual(result["stage"], "leaving")
            self.assertEqual(result["items"], ["A"])

    def test_scenarios_hold_across_click_intervals(self):
        # 상세페이지에 머무는 시간은 사람마다 다르다. 빠르게 눌러도 같은 단계가 나와야 한다.
        expected = {
            "ABCDEF": "browsing",
            "ABAAA": "decided",
            "ABABAB": "comparing",
            "AAABCDEF": "leaving",
        }
        for predictor in self.each_version():
            for seconds in [1, 5, 10, 20, 30]:
                for items, stage in expected.items():
                    with self.subTest(gap=seconds, items=items):
                        result = self.judge(predictor, items, gap=seconds * SECOND)
                        self.assertEqual(result["stage"], stage)

    def test_no_false_alarm_across_click_intervals(self):
        # 정답 단계를 정하기 애매한 흐름은 "잘못 띄우지 않는지"만 본다.
        # 모달을 잘못 띄우는 쪽이 놓치는 쪽보다 나쁘다.
        not_expected = [
            ("AAB", "comparing"),  # A 두 번 후 B를 한 번 열었을 뿐
            ("AAAB", "comparing"),
            ("AAABC", "comparing"),
            ("ABA", "decided"),  # 조회 3번, A 재방문 1번으로는 이르다
            ("ABCDEFGH", "decided"),  # 모두 다른 상품
            ("ABCDEFGH", "comparing"),
        ]
        for predictor in self.each_version():
            for seconds in [1, 5, 10, 20, 30]:
                for items, stage in not_expected:
                    with self.subTest(gap=seconds, items=items):
                        result = self.judge(predictor, items, gap=seconds * SECOND)
                        self.assertNotEqual(result["stage"], stage)


if __name__ == "__main__":
    unittest.main()
