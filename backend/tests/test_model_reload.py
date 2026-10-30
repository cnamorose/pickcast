"""ml.py의 ModelHolder가 current.json을 따라 재시작 없이 모델을 바꾸는지, 임시 모델 폴더로 확인한다.

실제 ml/models/는 건드리지 않는다. 모델 파일은 Git에 포함된 서비스 버전을 복사해 쓴다.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.app.ml import MODELS_DIR, ModelHolder
from release import current_version, use_version


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class ModelReloadTest(unittest.TestCase):
    def setUp(self):
        self.models = Path(tempfile.mkdtemp())
        base = current_version(MODELS_DIR)
        shutil.copytree(MODELS_DIR / base, self.models / "product_purchase_v1")
        shutil.copytree(MODELS_DIR / base, self.models / "product_purchase_v2")
        use_version("v1", self.models)
        self.clock = FakeClock()
        self.holder = ModelHolder(self.models, check_every=5, clock=self.clock)

    def tearDown(self):
        shutil.rmtree(self.models)

    def test_starts_with_current_version(self):
        self.assertEqual(self.holder.get().version, "product_purchase_v1")

    def test_switches_after_check_interval(self):
        use_version("v2", self.models)
        self.clock.now = 4
        self.assertEqual(self.holder.get().version, "product_purchase_v1")  # 아직 확인 전
        self.clock.now = 5
        self.assertEqual(self.holder.get().version, "product_purchase_v2")
        self.assertIsNone(self.holder.last_error)

    def test_roll_back(self):
        use_version("v2", self.models)
        self.clock.now = 5
        self.holder.get()
        use_version("v1", self.models)
        self.clock.now = 10
        self.assertEqual(self.holder.get().version, "product_purchase_v1")

    def test_same_version_keeps_same_object(self):
        first = self.holder.get()
        self.clock.now = 5
        self.assertIs(self.holder.get(), first)

    def test_broken_version_keeps_previous_model(self):
        broken = self.models / "product_purchase_v3"
        broken.mkdir()
        (broken / "calibration.json").write_text(json.dumps({"model": "missing"}), encoding="utf-8")
        # use_version은 깨진 폴더를 거부하므로 current.json을 직접 바꿔 사고 상황을 만든다
        (self.models / "current.json").write_text(json.dumps({"version": "product_purchase_v3"}), encoding="utf-8")
        self.clock.now = 5
        self.assertEqual(self.holder.get().version, "product_purchase_v1")
        self.assertIn("product_purchase_v3", self.holder.last_error)

    def test_recovers_after_broken_version_is_fixed(self):
        (self.models / "current.json").write_text(json.dumps({"version": "product_purchase_v9"}), encoding="utf-8")
        self.clock.now = 5
        self.holder.get()
        self.assertIsNotNone(self.holder.last_error)
        use_version("v2", self.models)
        self.clock.now = 10
        self.assertEqual(self.holder.get().version, "product_purchase_v2")
        self.assertIsNone(self.holder.last_error)


if __name__ == "__main__":
    unittest.main()
