"""replay_api.py가 저장된 재생 파일을 목록·하루치로 내주고 다음 10분 실제 판매를 붙이는지 확인한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app.replay_api import (
    REPLAY_DIR,
    actual_next_window,
    get_day,
    get_days,
    list_days,
    load_day,
)


def fake_replay(day="2015-08-17"):
    return {
        "date": day,
        "version": "product_purchase_v3",
        "minutes": 5,
        "horizon_minutes": 2,
        "summary": {"customers": 2, "purchases": 3},
        "snapshots": {"expected_next_10m": [0.1] * 5},
        "events": {"columns": ["second", "customer", "type", "item"], "rows": []},
        "purchases": {
            "columns": ["second", "customer", "item", "probability", "rank", "candidates", "minutes_before"],
            # 30초(모델이 본 구매), 60초(못 본 구매), 200초(본 구매)
            "rows": [
                [30.0, 1, 11, 0.2, 1, 2, 3.0],
                [60.0, 2, 12, None, None, None, None],
                [200.0, 1, 13, 0.1, 2, 2, 1.0],
            ],
        },
    }


class ActualNextWindowTest(unittest.TestCase):
    def test_counts_purchases_after_each_minute(self):
        # 2분 구간: 0분 → (0, 120]초, 1분 → (60, 180]초 (60초 정각은 0분 구간), ...
        counts = actual_next_window([30.0, 60.0, 200.0], 5, 2)
        self.assertEqual(counts, [2, 0, 1, 1, 0])


class ReplayFilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        for day in ["2015-08-17", "2015-08-07"]:
            (self.dir / f"{day}.json").write_text(json.dumps(fake_replay(day)), encoding="utf-8")
        (self.dir / "notes.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_list_days_in_date_order_with_weekday(self):
        days = list_days(self.dir)
        self.assertEqual([d["date"] for d in days], ["2015-08-07", "2015-08-17"])
        self.assertEqual([d["weekday"] for d in days], ["금", "월"])
        self.assertEqual(days[1]["purchases"], 3)

    def test_day_adds_actual_sales(self):
        day = load_day("2015-08-17", self.dir)
        self.assertEqual(day["weekday"], "월")
        self.assertEqual(day["actual_next_10m"], [2, 0, 1, 1, 0])
        self.assertEqual(day["actual_known_next_10m"], [1, 0, 1, 1, 0])

    def test_missing_day_is_404(self):
        with self.assertRaises(HTTPException) as caught:
            load_day("2015-08-01", self.dir)
        self.assertEqual(caught.exception.status_code, 404)

    def test_bad_date_is_400(self):
        for bad in ["../secret", "2015-8-1", "latest"]:
            with self.assertRaises(HTTPException) as caught:
                load_day(bad, self.dir)
            self.assertEqual(caught.exception.status_code, 400)


class RepositoryReplayTest(unittest.TestCase):
    def test_repository_days(self):
        days = get_days()["days"]
        self.assertIn("2015-08-17", [d["date"] for d in days])
        day = get_day(days[0]["date"])
        self.assertEqual(len(day["snapshots"]["expected_next_10m"]), day["minutes"])
        self.assertEqual(len(day["snapshots"]["top_items"]), day["minutes"])
        self.assertEqual(len(day["actual_next_10m"]), day["minutes"])
        self.assertLessEqual(sum(day["actual_known_next_10m"]), sum(day["actual_next_10m"]))
        self.assertTrue(REPLAY_DIR.exists())


if __name__ == "__main__":
    unittest.main()
