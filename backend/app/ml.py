import sys
from pathlib import Path

# ml/product_purchase 폴더를 Python import 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ML_DIR = PROJECT_ROOT / "ml" / "product_purchase"

sys.path.insert(0, str(ML_DIR))

from predict import FEATURE_LABELS, RELEASE_DIR, PurchasePredictor  # noqa: E402
from stage import judge_stage  # noqa: E402

# 서버가 시작될 때 ML 모델을 한 번만 로딩
predictor = PurchasePredictor()

# 세션에 기록할 모델 버전 (모델 폴더 이름)
MODEL_VERSION = RELEASE_DIR.name

__all__ = ["FEATURE_LABELS", "MODEL_VERSION", "judge_stage", "predictor"]
