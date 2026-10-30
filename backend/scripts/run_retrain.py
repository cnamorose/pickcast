"""재학습 한 번 실행: DB 체험 기록 내보내기 → ml 재학습 파이프라인. DB만 켜져 있으면 된다.

    python backend/scripts/run_retrain.py              # 스위치(ml/pipeline_config.json)에 따라 실행
    python backend/scripts/run_retrain.py --dry-run    # 스위치와 상관없이 평가까지만

배포 후 주기 실행에는 이 명령 하나만 등록한다. 종료 코드는 정상적으로 멈추면(스위치 꺼짐,
세션 부족, 등록 기준 미통과, 등록, 반영) 0, 오류면 1이다.
"""
import argparse
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlmodel import Session  # noqa: E402

from backend.app.db import engine  # noqa: E402
from backend.app.retrain import NORMAL_STOPS, run_retrain  # noqa: E402

from pipeline import MESSAGES, REFERENCE_PATH  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="체험 기록 내보내기 → 재학습 파이프라인")
    parser.add_argument("--dry-run", action="store_true", help="스위치와 상관없이 평가까지만 하고 등록하지 않음")
    args = parser.parse_args()

    if not REFERENCE_PATH.exists():
        print(f"참조 파일이 없습니다: {REFERENCE_PATH}")
        print("python ml/product_purchase/pipeline.py --build-reference 로 먼저 만드세요.")
        return 1
    try:
        with Session(engine) as db:
            export_path, report = run_retrain(db, dry_run=args.dry_run)
    except OperationalError as error:
        print(f"DB에 연결할 수 없습니다: {error.orig.__class__.__name__}")
        print("DB가 켜져 있는지 확인하세요 (로컬은 docker compose up -d).")
        return 1
    except Exception:
        traceback.print_exc()
        return 1

    print(f"내보내기: {export_path}")
    if "dataset" in report:
        d = report["dataset"]
        print(f"학습 데이터: 세션 {d['input_sessions']}개 중 {d['kept_sessions']}개 사용")
    for failure in report.get("gate", {}).get("failures", []):
        print(f"  - {failure}")
    if "registered" in report:
        print(f"등록: {report['registered']}")
    print(MESSAGES.get(report["stopped"], report["stopped"]))
    return 0 if report["stopped"] in NORMAL_STOPS else 1


if __name__ == "__main__":
    sys.exit(main())
