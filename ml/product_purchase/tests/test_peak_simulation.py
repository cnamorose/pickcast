"""peak_simulation.py의 처리 순서, 이탈, 에이징을 손으로 만든 요청으로 확인한다."""
import unittest

from peak_simulation import (
    REPLAY_WINDOWS_PATH,
    Request,
    choose_alpha,
    load_replay_windows,
    priority_key,
    replay,
    simulate,
)


def served_order(requests, capacity, policy, alpha=0.0, timeout=100):
    """처리된 순서를 점수로 돌려준다 (점수를 요청 구분용으로 씀)."""
    _, waits = simulate(requests, capacity, policy, alpha, timeout)
    return [score for score, _ in waits]


class OrderTest(unittest.TestCase):
    def setUp(self):
        # 같은 1초 안에 도착한 요청 3개, 서버는 1초에 1개
        self.requests = [
            Request(0.1, 1, 1.0, False),
            Request(0.2, 2, 5.0, True),
            Request(0.3, 3, 3.0, False),
        ]

    def test_fifo_serves_by_arrival(self):
        self.assertEqual(served_order(self.requests, 1, "fifo"), [1.0, 5.0, 3.0])

    def test_priority_serves_by_score(self):
        self.assertEqual(served_order(self.requests, 1, "priority"), [5.0, 3.0, 1.0])

    def test_aging_key_matches_score_plus_wait(self):
        # 점수 + α × 대기 시간의 순서와 "점수 − α × 도착 시각"의 순서는 언제나 같다
        a, b, alpha, now = Request(0.0, 1, 1.0, False), Request(9.0, 2, 2.0, False), 0.5, 10.0
        by_definition = (a.score + alpha * (now - a.arrival)) > (b.score + alpha * (now - b.arrival))
        by_key = priority_key(a, "aging", alpha) < priority_key(b, "aging", alpha)
        self.assertEqual(by_definition, by_key)


class StarvationTest(unittest.TestCase):
    def test_aging_serves_old_low_score_request(self):
        # 낮은 점수 요청 하나와, 1초에 2개씩 들어오는 높은 점수 요청들. 서버는 1초에 1개.
        requests = [Request(0.0, 0, 1.0, False)]
        requests += [Request(t + offset, 2 * t + k + 1, 2.0, False)
                     for t in range(30) for k, offset in enumerate([0.1, 0.5])]
        no_aging = served_order(requests, 1, "priority", timeout=100)
        with_aging = served_order(requests, 1, "aging", alpha=1.0, timeout=100)
        self.assertNotIn(1.0, no_aging[:20])  # 에이징이 없으면 계속 밀린다
        self.assertIn(1.0, with_aging[:3])  # 에이징이 있으면 곧 처리된다


class TimeoutTest(unittest.TestCase):
    def test_user_leaves_after_timeout_and_later_requests_are_dropped(self):
        # 서버는 1초에 1개, 1번 고객의 요청이 밀려 3초를 넘기면 떠나고 이후 요청도 버려진다
        requests = [Request(0.0, 9, 9.0, False) for _ in range(6)]
        requests += [Request(0.5, 1, 1.0, True), Request(5.0, 1, 1.0, True)]
        left, waits = simulate(requests, 1, "priority", timeout=3)
        self.assertIn(1, left)
        self.assertNotIn(1.0, [score for score, _ in waits])

    def test_no_overload_no_one_leaves(self):
        requests = [Request(float(t), t, 1.0, True) for t in range(10)]
        left, waits = simulate(requests, 5, "fifo", timeout=3)
        self.assertEqual(left, set())
        self.assertEqual(len(waits), 10)


class TraceTest(unittest.TestCase):
    def setUp(self):
        self.requests = [Request(0.0, 9, 9.0, False) for _ in range(6)]
        self.requests += [Request(0.5, 1, 1.0, True), Request(5.0, 1, 1.0, True), Request(6.0, 2, 3.0, False)]

    def test_trace_does_not_change_result(self):
        plain = simulate(self.requests, 1, "priority", timeout=3)
        trace = []
        traced = simulate(self.requests, 1, "priority", timeout=3, trace=trace)
        self.assertEqual(plain, traced)

    def test_every_request_is_accounted_for(self):
        trace = []
        left, waits = simulate(self.requests, 1, "priority", timeout=3, trace=trace)
        events = {e["event"] for e in trace}
        self.assertLessEqual(events, {"arrive", "ignored", "left", "served", "tick"})
        arrived = sum(1 for e in trace if e["event"] in ("arrive", "ignored"))
        self.assertEqual(arrived, len(self.requests))
        self.assertEqual(sum(1 for e in trace if e["event"] == "served"), len(waits))
        self.assertEqual({e["user"] for e in trace if e["event"] == "left"}, left)

    def test_tick_counts_are_cumulative(self):
        trace = []
        simulate(self.requests, 1, "fifo", timeout=3, trace=trace)
        ticks = [e for e in trace if e["event"] == "tick"]
        self.assertEqual([e["t"] for e in ticks], list(range(1, len(ticks) + 1)))
        self.assertEqual([e["served"] for e in ticks], sorted(e["served"] for e in ticks))

    def test_replay_summary(self):
        result = replay(self.requests, "fifo")
        summary = result["summary"]
        self.assertEqual(summary["buyers"], 1)
        self.assertEqual(summary["users"], 3)
        self.assertEqual(summary["served_requests"], sum(1 for e in result["events"] if e["event"] == "served"))


class ReplayWindowsTest(unittest.TestCase):
    def test_repository_windows_load(self):
        windows = load_replay_windows(REPLAY_WINDOWS_PATH)
        self.assertTrue(windows)
        for window in windows:
            self.assertGreater(window["buyers"], 0)
            self.assertTrue(all(isinstance(r, Request) for r in window["requests"]))


class ChooseAlphaTest(unittest.TestCase):
    def test_picks_best_within_fairness_limit(self):
        valid = {
            "results": [
                {"policy": "fifo", "alpha": 0.0, "protected_buyer_rate": 0.5, "low_left_rate": 0.30},
                {"policy": "priority", "alpha": 0.0, "protected_buyer_rate": 0.9, "low_left_rate": 0.60},
                {"policy": "aging", "alpha": 0.5, "protected_buyer_rate": 0.7, "low_left_rate": 0.33},
                {"policy": "aging", "alpha": 1.0, "protected_buyer_rate": 0.6, "low_left_rate": 0.31},
            ]
        }
        self.assertEqual(choose_alpha(valid), 0.5)


if __name__ == "__main__":
    unittest.main()
