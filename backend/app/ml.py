import logging
import sys
import threading
import time
from pathlib import Path

# ml/product_purchase 폴더를 Python import 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ML_DIR = PROJECT_ROOT / "ml" / "product_purchase"

sys.path.insert(0, str(ML_DIR))

from dashboard import compare_pairs, count_stages, forecast_sales  # noqa: E402
from predict import FEATURE_LABELS, PurchasePredictor  # noqa: E402
from release import MODELS_DIR, current_version, normalize, release_dir  # noqa: E402
from stage import judge_stage  # noqa: E402

logger = logging.getLogger(__name__)

# current.json이 바뀌었는지 이 간격(초)마다 확인한다. 매 요청마다 파일을 읽지 않기 위해서다.
CHECK_EVERY_SECONDS = 5


class ModelHolder:
    """서비스 모델을 들고 있다가 ml/models/current.json이 바뀌면 재시작 없이 새 버전을 불러온다.

    새 버전을 불러오다 실패하면(폴더가 깨졌다든지) 기존 모델을 계속 쓰고 last_error에 남긴다.
    """

    def __init__(self, models_dir=MODELS_DIR, check_every=CHECK_EVERY_SECONDS, clock=time.monotonic):
        self.models_dir = models_dir
        self.check_every = check_every
        self.clock = clock
        self.last_error = None
        self._lock = threading.Lock()
        self._predictor = PurchasePredictor(release_dir(models_dir=models_dir))
        self._checked_at = clock()

    def get(self):
        if self.clock() - self._checked_at >= self.check_every:
            with self._lock:
                if self.clock() - self._checked_at >= self.check_every:
                    self._checked_at = self.clock()
                    self._reload_if_changed()
        return self._predictor

    def _reload_if_changed(self):
        try:
            version = normalize(current_version(self.models_dir))
        except Exception as error:  # current.json을 읽지 못하면 지금 모델을 유지
            self.last_error = f"current.json을 읽지 못함: {error}"
            logger.error(self.last_error)
            return
        if version == self._predictor.version:
            return
        try:
            predictor = PurchasePredictor(release_dir(version, self.models_dir))
        except Exception as error:
            self.last_error = f"{version}을 불러오지 못해 {self._predictor.version}을 계속 씀: {error}"
            logger.error(self.last_error)
            return
        logger.info("모델 교체: %s → %s", self._predictor.version, version)
        self._predictor = predictor
        self.last_error = None


# 서버가 시작될 때 지금 서비스 버전을 불러오고, 이후에는 current.json을 따라간다
models = ModelHolder()


def get_predictor():
    """지금 서비스 모델. 한 요청 안에서는 한 번만 꺼내 같은 모델로 계산한다."""
    return models.get()


__all__ = [
    "FEATURE_LABELS",
    "compare_pairs",
    "count_stages",
    "forecast_sales",
    "get_predictor",
    "judge_stage",
    "models",
]
