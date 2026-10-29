"""experience.py의 정제·학습 행·분리·저장과 pipeline_config.py를 손으로 만든 기록으로 확인한다.

RetailRocket 학습 데이터와 같은 규칙인지는 고객 300명(학습 행 15,855개)을 기존
학습 데이터와 비교해 모두 같음을 확인했다 (원본 데이터가 필요해 테스트에는 넣지 않음).
"""
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from experience import build_dataset, clean_sessions, session_rows, split_of
from pipeline_config import DEFAULTS, load_pipeline_config

SECOND = 1000


def records(session, views, purchases=(), status="purchased", mode="experience", gap=5 * SECOND):
    rows = [
        {"session_id": session, "event": "view", "item_id": item, "timestamp": k * gap,
         "status": status, "kind": "virtual", "mode": mode}
        for k, item in enumerate(views)
    ]
    rows += [
        {"session_id": session, "event": "purchase", "item_id": item, "timestamp": t,
         "status": status, "kind": "virtual", "mode": mode}
        for t, item in purchases
    ]
    return rows


class CleanSessionsTest(unittest.TestCase):
    def clean(self, *sessions):
        frame = pd.DataFrame([row for session in sessions for row in session])
        return clean_sessions(frame)

    def test_keeps_finished_experience_sessions(self):
        kept, report = self.clean(records("a", "ABA"), records("b", "AB", status="abandoned"))
        self.assertEqual(report["kept_sessions"], 2)
        self.assertEqual(report["removed_sessions"], {})

    def test_removes_each_reason(self):
        kept, report = self.clean(
            records("active", "ABA", status="active"),
            records("seed", "ABA", mode="simulated"),
            records("many", ["P"] * 100),
            records("fast", "ABAB", gap=300),
            records("ok", "ABA"),
        )
        self.assertEqual(
            report["removed_sessions"],
            {"not_finished": 1, "not_experience": 1, "too_many_views": 1, "too_fast": 1},
        )
        self.assertEqual(set(kept["session_id"]), {"ok"})

    def test_short_fast_session_is_not_judged_by_speed(self):
        # 조회 2번은 간격이 짧아도 속도로 판단하지 않는다
        _, report = self.clean(records("two", "AB", gap=100))
        self.assertEqual(report["kept_sessions"], 1)

    def test_duplicate_rows_removed(self):
        session = records("a", "ABA")
        _, report = self.clean(session + [session[0]])
        self.assertEqual(report["duplicate_rows_removed"], 1)


class SessionRowsTest(unittest.TestCase):
    def test_label_marks_item_bought_later(self):
        rows, _ = session_rows([(0, "A"), (10, "B"), (20, "A")], [(30, "A")])
        labels = {(r["cutoff_timestamp"], r["item_id"]): r["label"] for r in rows}
        self.assertEqual(labels[(0, "A")], 1)
        self.assertEqual(labels[(10, "B")], 0)
        self.assertEqual(labels[(20, "A")], 1)

    def test_bought_item_leaves_candidates(self):
        rows, _ = session_rows([(0, "A"), (10, "B"), (40, "C")], [(20, "A")])
        later = [r["item_id"] for r in rows if r["cutoff_timestamp"] == 40]
        self.assertEqual(sorted(later), ["B", "C"])

    def test_same_time_view_and_purchase_point_is_excluded(self):
        rows, excluded = session_rows([(0, "A"), (10, "A")], [(10, "A")])
        self.assertEqual(excluded, 1)
        self.assertEqual({r["cutoff_timestamp"] for r in rows}, {0})

    def test_features_match_view_counts(self):
        rows, _ = session_rows([(0, "A"), (10, "B"), (20, "A")], [])
        last_a = [r for r in rows if r["cutoff_timestamp"] == 20 and r["item_id"] == "A"][0]
        self.assertEqual(last_a["view_count"], 2)
        self.assertEqual(last_a["revisit_count"], 1)
        self.assertEqual(last_a["is_last_viewed"], 1)


class SplitTest(unittest.TestCase):
    def test_same_session_same_split(self):
        self.assertEqual(split_of("abc"), split_of("abc"))

    def test_about_twenty_percent_eval(self):
        counts = Counter(split_of(f"session-{k}") for k in range(5000))
        self.assertAlmostEqual(counts["eval"] / 5000, 0.2, delta=0.03)


class BuildDatasetTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        frame = pd.DataFrame(
            records("a", "ABAA", purchases=[(100 * SECOND, "A")])
            + records("b", "ABC", status="abandoned")
            + records("seed", "ABA", mode="simulated")
        )
        self.input = self.root / "sessions.csv"
        frame.to_csv(self.input, index=False)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_writes_rows_and_report(self):
        target, report = build_dataset(self.input, self.root / "out", version="v-test")
        rows = pd.read_parquet(target / "training_rows.parquet")
        self.assertEqual(set(rows["session_id"]), {"a", "b"})
        self.assertEqual(report["removed_sessions"], {"not_experience": 1})
        self.assertEqual(report["rows"], len(rows))
        self.assertTrue((rows.loc[rows["session_id"] == "a", "item_id"] == "A").any())
        saved = json.loads((target / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["kept_sessions"], 2)

    def test_does_not_overwrite_version(self):
        build_dataset(self.input, self.root / "out", version="v-test")
        with self.assertRaises(FileExistsError):
            build_dataset(self.input, self.root / "out", version="v-test")


class PipelineConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write(self, config):
        path = self.dir / "pipeline_config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def test_missing_file_means_off(self):
        self.assertEqual(load_pipeline_config(self.dir / "none.json"), DEFAULTS)
        self.assertFalse(DEFAULTS["retrain_enabled"])
        self.assertFalse(DEFAULTS["auto_release"])

    def test_turn_on(self):
        config = load_pipeline_config(self.write({"retrain_enabled": True}))
        self.assertTrue(config["retrain_enabled"])
        self.assertFalse(config["auto_release"])

    def test_rejects_non_boolean_switch(self):
        with self.assertRaises(ValueError):
            load_pipeline_config(self.write({"retrain_enabled": "true"}))

    def test_rejects_unknown_key(self):
        with self.assertRaises(ValueError):
            load_pipeline_config(self.write({"retrain_enabeld": True}))

    def test_repository_config_is_valid(self):
        load_pipeline_config()


if __name__ == "__main__":
    unittest.main()
