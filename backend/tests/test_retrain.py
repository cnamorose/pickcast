"""retrain.py가 DB 내보내기 → 파이프라인으로 이어지는지 메모리 DB와 임시 폴더로 확인한다."""
import shutil
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from backend.app.models import ShoppingSession, View
from backend.app.retrain import NORMAL_STOPS, run_retrain


class RetrainTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        self.db = Session(engine)
        self.db.add(ShoppingSession(id="a", status="abandoned"))
        for k, item in enumerate(["TOP-01", "TOP-02", "TOP-01"]):
            self.db.add(View(session_id="a", item_id=item, timestamp=k * 5000))
        self.db.commit()
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.root)

    def run_retrain(self, **config):
        settings = {"retrain_enabled": True, "auto_release": False, "min_sessions": 50, **config}
        return run_retrain(
            self.db,
            export_dir=self.root / "exports",
            config=settings,
            experience_root=self.root / "experience",
        )

    def test_switch_off_exports_then_stops(self):
        export_path, report = self.run_retrain(retrain_enabled=False)
        self.assertTrue(export_path.exists())
        self.assertEqual(report["stopped"], "retrain_disabled")

    def test_runs_pipeline_on_exported_file(self):
        export_path, report = self.run_retrain()
        self.assertEqual(report["dataset"]["input"], str(export_path))
        self.assertEqual(report["dataset"]["kept_sessions"], 1)
        self.assertEqual(report["stopped"], "not_enough_sessions")
        self.assertIn(report["stopped"], NORMAL_STOPS)


if __name__ == "__main__":
    unittest.main()
