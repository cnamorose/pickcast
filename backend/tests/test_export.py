"""export.py의 내보내기 형식을 메모리 DB로 확인한다. 실제 DB는 쓰지 않는다."""
import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from backend.app.export import COLUMNS, EXPIRE_AFTER_MINUTES, export_rows, write_csv
from backend.app.models import Purchase, ShoppingSession, View

# 테스트 기록의 시각(ms)은 1970년 근처라, 만료를 보려면 now_ms를 직접 넘긴다
JUST_AFTER = 10_000
LONG_AFTER = 700 + EXPIRE_AFTER_MINUTES * 60_000 + 1


class ExportTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        self.db = Session(engine)
        self.db.add(ShoppingSession(id="bought", status="purchased"))
        self.db.add(ShoppingSession(id="seed", status="abandoned", mode="simulated"))
        self.db.add(ShoppingSession(id="open"))
        self.db.add(View(session_id="bought", item_id="TOP-01", timestamp=2000))
        self.db.add(View(session_id="bought", item_id="TOP-02", timestamp=1000))
        self.db.add(Purchase(session_id="bought", item_id="TOP-01", timestamp=3000))
        self.db.add(View(session_id="seed", item_id="BAG-01", timestamp=500))
        self.db.add(View(session_id="open", item_id="SHOES-01", timestamp=700))
        self.db.commit()
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.dir)

    def test_rows_have_session_info(self):
        rows = export_rows(self.db, now_ms=JUST_AFTER)
        bought = [r for r in rows if r["session_id"] == "bought"]
        self.assertEqual([r["event"] for r in bought], ["view", "view", "purchase"])
        self.assertEqual([r["timestamp"] for r in bought], [1000, 2000, 3000])
        self.assertTrue(all(r["status"] == "purchased" and r["mode"] == "experience" for r in bought))
        self.assertEqual(bought[-1]["kind"], "virtual")

    def test_exports_every_session(self):
        # 무엇을 학습에 쓸지는 ml 쪽 정제가 정한다
        rows = export_rows(self.db, now_ms=JUST_AFTER)
        modes = {r["session_id"]: (r["mode"], r["status"]) for r in rows}
        self.assertEqual(modes["seed"], ("simulated", "abandoned"))
        self.assertEqual(modes["open"], ("experience", "active"))

    def test_idle_active_session_is_exported_as_abandoned(self):
        rows = export_rows(self.db, now_ms=LONG_AFTER)
        status = {r["session_id"]: r["status"] for r in rows}
        self.assertEqual(status["open"], "abandoned")
        self.assertEqual(status["bought"], "purchased")
        # DB 값은 바꾸지 않는다
        self.assertEqual(self.db.get(ShoppingSession, "open").status, "active")

    def test_csv_columns(self):
        path = write_csv(export_rows(self.db, now_ms=JUST_AFTER), self.dir / "out" / "sessions.csv")
        with open(path, encoding="utf-8") as file:
            reader = csv.DictReader(file)
            self.assertEqual(reader.fieldnames, COLUMNS)
            self.assertEqual(len(list(reader)), 5)


if __name__ == "__main__":
    unittest.main()
