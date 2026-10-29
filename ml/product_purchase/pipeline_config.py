"""배치 재학습 파이프라인 스위치. ml/pipeline_config.json을 읽는다.

    retrain_enabled  체험 데이터로 재보정·재학습을 돌릴지 (배포 후 데이터가 쌓이면 켠다)
    auto_release     등록 기준을 통과한 새 버전을 서비스에 자동 반영할지.
                     false면 새 버전을 등록만 하고 반영은 사람이 release.py use로 한다.
    min_sessions     학습에 쓸 수 있는 체험 세션이 이만큼 쌓여야 재보정을 실행한다

스위치는 자동 실행(파이프라인)이 확인한다. 체험 기록을 학습 데이터로 바꾸는 것
(experience.py)이나 사람이 직접 돌리는 재보정(recalibrate.py)은 스위치와 상관없이 실행된다.
"""
import json
from pathlib import Path

from events import ml_dir

CONFIG_PATH = ml_dir / "pipeline_config.json"
DEFAULTS = {"retrain_enabled": False, "auto_release": False, "min_sessions": 50}


def load_pipeline_config(path=CONFIG_PATH):
    """설정 파일을 읽는다. 파일이나 항목이 없으면 꺼진 상태(DEFAULTS)로 본다."""
    path = Path(path)
    config = dict(DEFAULTS)
    if path.exists():
        config.update(json.loads(path.read_text(encoding="utf-8")))
    unknown = set(config) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"알 수 없는 설정: {sorted(unknown)}")
    for name in ("retrain_enabled", "auto_release"):
        if not isinstance(config[name], bool):
            raise ValueError(f"{name}은 true 또는 false여야 합니다: {config[name]!r}")
    if not isinstance(config["min_sessions"], int) or config["min_sessions"] < 1:
        raise ValueError(f"min_sessions는 1 이상의 정수여야 합니다: {config['min_sessions']!r}")
    return config
