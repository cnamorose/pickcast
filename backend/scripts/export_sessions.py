"""DB의 체험 기록을 재학습용 CSV로 내보낸다. 서버를 띄우지 않아도 DB만 켜져 있으면 된다.

    python backend/scripts/export_sessions.py
    python backend/scripts/export_sessions.py --output exports/sessions.csv

기본 저장 위치는 ml/data/experience/exports/sessions-<시각>.csv이며 Git에 올라가지 않는다.
내보낸 파일은 ml 쪽에서 학습 데이터로 바꾼다:

    python ml/product_purchase/experience.py <내보낸 파일>
"""
import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlmodel import Session  # noqa: E402

from backend.app.db import engine  # noqa: E402
from backend.app.export import export_rows, write_csv  # noqa: E402

DEFAULT_DIR = PROJECT_ROOT / "ml" / "data" / "experience" / "exports"


def main():
    parser = argparse.ArgumentParser(description="체험 기록을 재학습용 CSV로 내보낸다")
    parser.add_argument("--output", type=Path, help="저장할 CSV 경로")
    args = parser.parse_args()
    output = args.output or DEFAULT_DIR / f"sessions-{datetime.now():%Y%m%d-%H%M%S}.csv"

    with Session(engine) as db:
        rows = export_rows(db)
    write_csv(rows, output)

    sessions = {(r["session_id"], r["mode"], r["status"]) for r in rows}
    by_kind = Counter((mode, status) for _, mode, status in sessions)
    print(f"기록 {len(rows):,}줄, 세션 {len(sessions):,}개")
    for (mode, status), count in sorted(by_kind.items()):
        print(f"  {mode:<11} {status:<10} {count:,}개")
    print(f"저장: {output}")


if __name__ == "__main__":
    main()
