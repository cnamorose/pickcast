"""release.py의 버전 선택·전환을 임시 폴더로 확인한다. 실제 ml/models/는 건드리지 않는다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from release import (
    MODELS_DIR,
    current_version,
    list_versions,
    next_version,
    normalize,
    register_version,
    release_dir,
    use_version,
)


def make_version(models_dir, name, with_model=True):
    directory = models_dir / name
    directory.mkdir()
    (directory / "calibration.json").write_text(json.dumps({"model": "m"}), encoding="utf-8")
    if with_model:
        (directory / "m.txt").write_text("model", encoding="utf-8")
    return directory


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.models_dir = Path(tempfile.mkdtemp())
        make_version(self.models_dir, "product_purchase_v1")
        make_version(self.models_dir, "product_purchase_v2")
        use_version("v1", self.models_dir)

    def tearDown(self):
        shutil.rmtree(self.models_dir)

    def test_short_name(self):
        self.assertEqual(normalize("v2"), "product_purchase_v2")
        self.assertEqual(normalize("product_purchase_v2"), "product_purchase_v2")

    def test_current_points_to_version_folder(self):
        self.assertEqual(current_version(self.models_dir), "product_purchase_v1")
        self.assertEqual(release_dir(models_dir=self.models_dir).name, "product_purchase_v1")

    def test_use_and_roll_back(self):
        use_version("v2", self.models_dir)
        self.assertEqual(current_version(self.models_dir), "product_purchase_v2")
        use_version("v1", self.models_dir)
        self.assertEqual(current_version(self.models_dir), "product_purchase_v1")

    def test_missing_version_is_rejected(self):
        with self.assertRaises(ValueError):
            use_version("v9", self.models_dir)
        self.assertEqual(current_version(self.models_dir), "product_purchase_v1")

    def test_version_without_model_file_is_rejected(self):
        make_version(self.models_dir, "product_purchase_v3", with_model=False)
        with self.assertRaises(ValueError):
            use_version("v3", self.models_dir)
        self.assertEqual(current_version(self.models_dir), "product_purchase_v1")

    def test_next_version_number(self):
        self.assertEqual(next_version(self.models_dir), "product_purchase_v3")

    def test_register_copies_model_and_keeps_current(self):
        calibration = {"method": "isotonic_smooth", "x_logit": [0.0], "y": [0.01]}
        directory = register_version("v3", "v2", calibration, 0.04, {"created": "2026-10-29"}, self.models_dir)
        self.assertTrue((directory / "m.txt").exists())
        saved = json.loads((directory / "calibration.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["model"], "m")
        self.assertEqual(saved["threshold"], 0.04)
        self.assertEqual(json.loads((directory / "metadata.json").read_text(encoding="utf-8"))["version"],
                         "product_purchase_v3")
        self.assertEqual(current_version(self.models_dir), "product_purchase_v1")

    def test_register_does_not_overwrite(self):
        with self.assertRaises(FileExistsError):
            register_version("v2", "v1", {}, 0.04, {}, self.models_dir)

    def test_list_marks_broken_versions(self):
        make_version(self.models_dir, "product_purchase_v3", with_model=False)
        problems = {v["version"]: v["problem"] for v in list_versions(self.models_dir)}
        self.assertIsNone(problems["product_purchase_v1"])
        self.assertIsNotNone(problems["product_purchase_v3"])


class RepositoryModelsTest(unittest.TestCase):
    """Git에 포함된 ml/models/가 서비스에 쓸 수 있는 상태인지 확인한다."""

    def test_current_version_is_usable(self):
        version = current_version(MODELS_DIR)
        problems = {v["version"]: v["problem"] for v in list_versions(MODELS_DIR)}
        self.assertIn(version, problems)
        self.assertIsNone(problems[version])


if __name__ == "__main__":
    unittest.main()
