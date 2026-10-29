"""pipeline.py의 단계별 멈춤, 등록, 반영을 임시 폴더와 가짜 체험 기록으로 확인한다.

실제 ml/models/와 ml/data/는 건드리지 않는다. 모델 파일은 Git에 포함된 서비스 버전을 복사해 쓴다.
"""
import json
import random
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pandas as pd

import pipeline
from experience import session_rows
from features import FEATURES
from release import MODELS_DIR, current_version, use_version

SECOND = 1000
PRODUCTS = [f"TOP-0{n}" for n in range(1, 9)]


def fake_session(rng, session_id):
    """사람처럼 5~20초 간격으로 보는 세션. 많이 본 상품을 살 가능성이 높게 만든다."""
    favorite = rng.choice(PRODUCTS)
    views, t = [], 0
    for _ in range(rng.randint(3, 8)):
        t += rng.randint(5, 20) * SECOND
        views.append((t, favorite if rng.random() < 0.5 else rng.choice(PRODUCTS)))
    purchases = [(t + 30 * SECOND, favorite)] if rng.random() < 0.3 else []
    return session_id, views, purchases


def export_frame(sessions):
    rows = []
    for session_id, views, purchases in sessions:
        status = "purchased" if purchases else "abandoned"
        for t, item in views:
            rows.append([session_id, "view", item, t, status, "", "experience"])
        for t, item in purchases:
            rows.append([session_id, "purchase", item, t, status, "virtual", "experience"])
    return pd.DataFrame(
        rows, columns=["session_id", "event", "item_id", "timestamp", "status", "kind", "mode"]
    )


def reference_frame(sessions):
    rows = []
    for k, (_, views, purchases) in enumerate(sessions):
        built, _ = session_rows(views, purchases)
        for row in built:
            rows.append({**{name: row[name] for name in FEATURES}, "label": row["label"],
                         "half": "A" if k % 2 == 0 else "B"})
    return pd.DataFrame(rows)


def passing():
    """등록 기준(확률 지표, 단계 판단)을 모두 통과한 것으로 둔다. 흐름만 확인하기 위해서다."""
    stack = ExitStack()
    stack.enter_context(mock.patch.object(pipeline, "gate", return_value=[]))
    stack.enter_context(mock.patch.object(pipeline, "scenario_mismatches", return_value=[]))
    return stack


class PipelineRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(7)
        cls.export = export_frame([fake_session(rng, f"s{k}") for k in range(300)])
        cls.reference = reference_frame([fake_session(rng, f"r{k}") for k in range(600)])

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.models = self.root / "models"
        self.models.mkdir()
        version = current_version(MODELS_DIR)
        shutil.copytree(MODELS_DIR / version, self.models / version)
        use_version(version, self.models)
        self.base = version
        self.export_path = self.root / "sessions.csv"
        self.export.to_csv(self.export_path, index=False)
        self.reference_path = self.root / "reference.parquet"
        self.reference.to_parquet(self.reference_path, index=False)

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_pipeline(self, dry_run=False, **config):
        settings = {"retrain_enabled": True, "auto_release": False, "min_sessions": 50, **config}
        return pipeline.run(
            self.export_path,
            dry_run=dry_run,
            config=settings,
            models_dir=self.models,
            experience_root=self.root / "experience",
            reference_path=self.reference_path,
        )

    def versions(self):
        return sorted(p.name for p in self.models.iterdir() if p.is_dir())

    def test_switch_off_stops_before_anything(self):
        report = self.run_pipeline(retrain_enabled=False)
        self.assertEqual(report["stopped"], "retrain_disabled")
        self.assertFalse((self.root / "experience").exists())

    def test_not_enough_sessions(self):
        report = self.run_pipeline(min_sessions=10_000)
        self.assertEqual(report["stopped"], "not_enough_sessions")
        self.assertEqual(self.versions(), [self.base])

    def test_dry_run_runs_with_switch_off_but_does_not_register(self):
        with passing():
            report = self.run_pipeline(dry_run=True, retrain_enabled=False)
        self.assertEqual(report["stopped"], "dry_run")
        self.assertIn("candidate", report)
        self.assertEqual(self.versions(), [self.base])

    def test_gate_failure_does_not_register(self):
        with mock.patch.object(pipeline, "gate", return_value=["테스트용 실패"]):
            report = self.run_pipeline()
        self.assertEqual(report["stopped"], "gate_failed")
        self.assertEqual(self.versions(), [self.base])

    def test_stage_mismatch_does_not_register(self):
        with mock.patch.object(pipeline, "gate", return_value=[]), mock.patch.object(
            pipeline, "scenario_mismatches", return_value=[("ABAAA", 20, "browsing")]
        ):
            report = self.run_pipeline(auto_release=True)
        self.assertEqual(report["stopped"], "gate_failed")
        self.assertIn("단계 판단", report["gate"]["failures"][0])
        self.assertEqual(self.versions(), [self.base])
        self.assertEqual(current_version(self.models), self.base)

    def test_registers_next_version_without_release(self):
        with passing():
            report = self.run_pipeline(auto_release=False)
        new = report["registered"]
        self.assertEqual(report["stopped"], "registered")
        self.assertIn(new, self.versions())
        self.assertEqual(current_version(self.models), self.base)
        metadata = json.loads((self.models / new / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["based_on"], self.base)

    def test_auto_release_switches_current(self):
        with passing():
            report = self.run_pipeline(auto_release=True)
        self.assertEqual(report["stopped"], "released")
        self.assertEqual(current_version(self.models), report["released"])

    def test_report_is_saved_with_dataset(self):
        report = self.run_pipeline(min_sessions=10_000)
        saved = Path(report["dataset"]["path"]) / "pipeline_report.json"
        self.assertEqual(json.loads(saved.read_text(encoding="utf-8"))["stopped"], "not_enough_sessions")


def metrics(log_loss, mean, positive):
    return {"rows": 100, "log_loss": log_loss, "mean_prediction": mean, "positive_rate": positive}


class GateTest(unittest.TestCase):
    def setUp(self):
        self.current = {"experience_eval": metrics(0.10, 0.03, 0.02), "public_b": metrics(0.0456, 0.009, 0.009)}

    def candidate(self, exp, public):
        return {"experience_eval": exp, "public_b": public}

    def test_better_on_experience_and_same_on_public_passes(self):
        new = self.candidate(metrics(0.09, 0.022, 0.02), metrics(0.0457, 0.009, 0.009))
        self.assertEqual(pipeline.gate(self.current, new), [])

    def test_worse_on_experience_fails(self):
        new = self.candidate(metrics(0.11, 0.04, 0.02), metrics(0.0456, 0.009, 0.009))
        self.assertEqual(len(pipeline.gate(self.current, new)), 2)

    def test_public_degradation_beyond_tolerance_fails(self):
        worse = 0.0456 * (1 + 2 * pipeline.PUBLIC_LOG_LOSS_TOLERANCE)
        new = self.candidate(metrics(0.09, 0.022, 0.02), metrics(worse, 0.009, 0.009))
        failures = pipeline.gate(self.current, new)
        self.assertEqual(len(failures), 1)
        self.assertIn("공개 데이터", failures[0])

    def test_no_purchase_in_experience_eval_fails(self):
        new = self.candidate(metrics(0.01, 0.01, 0.0), metrics(0.0456, 0.009, 0.009))
        self.assertIn("구매가 없어", pipeline.gate(self.current, new)[0])


if __name__ == "__main__":
    unittest.main()
