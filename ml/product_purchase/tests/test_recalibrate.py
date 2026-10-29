"""recalibrate.py의 등록 기준(gate)을 손으로 만든 지표로 확인한다."""
import unittest

from recalibrate import RANKING_TOLERANCE, gate


def version(mean, positive, log_loss, brier, auc, ap, dashboard_gap):
    return {
        "probability": {
            "mean_prediction": mean,
            "positive_rate": positive,
            "log_loss": log_loss,
            "brier": brier,
            "roc_auc": auc,
            "ap": ap,
        },
        "dashboard_gap": dashboard_gap,
    }


V1 = version(0.0103, 0.0087, 0.0457, 0.00852, 0.756, 0.035, 0.54)


class GateTest(unittest.TestCase):
    def test_better_on_every_item_passes(self):
        v2 = version(0.0094, 0.0087, 0.0455, 0.00851, 0.756, 0.035, 0.40)
        self.assertEqual(gate(V1, v2), [])

    def test_worse_calibration_fails(self):
        v2 = version(0.0110, 0.0087, 0.0458, 0.00853, 0.756, 0.035, 0.60)
        self.assertEqual(len(gate(V1, v2)), 4)

    def test_ranking_drop_beyond_tolerance_fails(self):
        v2 = version(0.0094, 0.0087, 0.0455, 0.00851, 0.756 - 2 * RANKING_TOLERANCE, 0.035, 0.40)
        failures = gate(V1, v2)
        self.assertEqual(len(failures), 1)
        self.assertIn("roc_auc", failures[0])

    def test_small_ranking_change_is_allowed(self):
        v2 = version(0.0094, 0.0087, 0.0455, 0.00851, 0.756 - RANKING_TOLERANCE / 2, 0.035, 0.40)
        self.assertEqual(gate(V1, v2), [])

    def test_over_correction_counts_as_gap(self):
        # 예측이 실제보다 더 크게 낮아지면 차이가 줄지 않은 것
        v2 = version(0.0060, 0.0087, 0.0455, 0.00851, 0.756, 0.035, -0.60)
        failures = gate(V1, v2)
        self.assertTrue(any("평균 예측" in f for f in failures))
        self.assertTrue(any("대시보드" in f for f in failures))


if __name__ == "__main__":
    unittest.main()
