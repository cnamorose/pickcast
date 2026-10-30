"""peak_api.py가 저장된 시뮬레이션 요약과 재생 결과를 내주는지 확인한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app.peak_api import (
    RESULTS_PATH,
    get_replay,
    get_windows,
    load_results,
    load_windows,
)


class PeakResultsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_returns_saved_summary(self):
        path = self.dir / "peak.json"
        path.write_text(json.dumps({"settings": {"chosen_alpha": 20.0}}), encoding="utf-8")
        self.assertEqual(load_results(path)["settings"]["chosen_alpha"], 20.0)

    def test_missing_file_is_404(self):
        for loader in (load_results, load_windows):
            with self.assertRaises(HTTPException) as caught:
                loader(self.dir / "none.json")
            self.assertEqual(caught.exception.status_code, 404)

    def test_repository_summary_has_three_policies_and_curves(self):
        results = load_results(RESULTS_PATH)
        self.assertEqual(set(results["test"]), {"fifo", "priority", "aging"})
        self.assertTrue(results["valid_alpha_curve"])
        self.assertTrue(results["test_alpha_curve"])


class PeakReplayTest(unittest.TestCase):
    def test_windows_list(self):
        windows = get_windows()["windows"]
        self.assertTrue(windows)
        self.assertEqual([w["window"] for w in windows], list(range(len(windows))))
        self.assertTrue(all(w["buyers"] > 0 and w["requests"] > 0 for w in windows))

    def test_replay_returns_events_and_summary(self):
        result = get_replay(window=0, policy="aging", alpha=20.0, overload=1.5)
        self.assertEqual(result["window"], 0)
        self.assertEqual(result["policy"], "aging")
        events = {e["event"] for e in result["events"]}
        self.assertTrue({"arrive", "served", "tick"} <= events)
        summary = result["summary"]
        self.assertLessEqual(summary["protected_buyers"], summary["buyers"])

    def test_alpha_is_ignored_for_non_aging(self):
        result = get_replay(window=0, policy="fifo", alpha=50.0, overload=1.5)
        self.assertEqual(result["alpha"], 0.0)

    def test_policies_differ_on_same_window(self):
        fifo = get_replay(window=0, policy="fifo", alpha=0.0, overload=1.5)["summary"]
        priority = get_replay(window=0, policy="priority", alpha=0.0, overload=1.5)["summary"]
        self.assertEqual(fifo["users"], priority["users"])
        self.assertNotEqual(fifo["left_users"], priority["left_users"])

    def test_less_overload_fewer_leave(self):
        heavy = get_replay(window=0, policy="fifo", alpha=0.0, overload=2.0)["summary"]
        light = get_replay(window=0, policy="fifo", alpha=0.0, overload=1.0)["summary"]
        self.assertLessEqual(light["left_users"], heavy["left_users"])

    def test_unknown_window_is_404(self):
        with self.assertRaises(HTTPException) as caught:
            get_replay(window=999, policy="fifo", alpha=0.0, overload=1.5)
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
