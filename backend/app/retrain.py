"""재학습 한 번 실행: DB 체험 기록 내보내기 → ml 재학습 파이프라인.

배포 후 서버의 주기 실행(cron 등)에는 backend/scripts/run_retrain.py 하나만 등록한다.
재학습을 할지(retrain_enabled), 새 버전을 자동 반영할지(auto_release)는 파이프라인이
ml/pipeline_config.json을 보고 정한다. 자동 반영되면 백엔드는 재시작 없이 새 모델을 쓴다(ml.py).
"""
from datetime import datetime
from pathlib import Path

from .export import export_rows, write_csv
from .ml import PROJECT_ROOT  # ml/product_purchase를 import 경로에 넣는다

from pipeline import run as run_pipeline  # noqa: E402  (ml/product_purchase/pipeline.py)

EXPORT_DIR = PROJECT_ROOT / "ml" / "data" / "experience" / "exports"

# 파이프라인이 정상적으로 멈춘 경우. 이 밖의 결과는 실패로 본다.
NORMAL_STOPS = {"retrain_disabled", "not_enough_sessions", "gate_failed", "dry_run", "registered", "released"}


def run_retrain(db, export_dir=EXPORT_DIR, dry_run=False, **pipeline_options):
    """기록을 내보내고 파이프라인을 실행한다. (내보낸 파일 경로, 파이프라인 리포트)를 돌려준다."""
    export_path = Path(export_dir) / f"sessions-{datetime.now():%Y%m%d-%H%M%S}.csv"
    write_csv(export_rows(db), export_path)
    report = run_pipeline(export_path, dry_run=dry_run, **pipeline_options)
    return export_path, report
