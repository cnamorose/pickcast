"""peak_api.py가 저장된 시뮬레이션 요약을 내주는지 확인한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app.peak_api import RESULTS_PATH, load_results


class PeakApiTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_returns_saved_summary(self):
        path = self.dir / "peak.json"
        path.write_text(json.dumps({"settings": {"chosen_alpha": 20.0}}), encoding="utf-8")
        self.assertEqual(load_results(path)["settings"]["chosen_alpha"], 20.0)

    def test_missing_file_is_404(self):
        with self.assertRaises(HTTPException) as caught:
            load_results(self.dir / "none.json")
        self.assertEqual(caught.exception.status_code, 404)

    def test_repository_summary_has_three_policies(self):
        results = load_results(RESULTS_PATH)
        self.assertEqual(set(results["test"]), {"fifo", "priority", "aging"})
        self.assertTrue(results["valid_alpha_curve"])


if __name__ == "__main__":
    unittest.main()
