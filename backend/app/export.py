"""재학습용 체험 기록 내보내기. DB의 조회·결제 기록을 세션 정보와 함께 한 표로 만든다.

ml 쪽(ml/product_purchase/experience.py)이 이 파일을 읽어 정제하고 학습 데이터로 바꾼다.
ml 코드가 DB에 직접 접속하지 않도록 백엔드가 파일로 넘긴다.

    session_id, event(view/purchase), item_id, timestamp(ms), status, kind, mode

쇼핑 중이거나 가상 손님(simulated)인 세션도 그대로 내보낸다. 무엇을 학습에 쓸지는
ml 쪽 정제 기준이 정하고, 뺀 이유를 리포트에 남긴다.

결제 없이 탭을 닫은 세션은 DB에서 계속 active로 남는다 (abandoned는 같은 브라우저에서
다시 시작할 때만 기록된다). 그대로 두면 이런 체험은 학습에 쓰이지 못하므로, 마지막 기록 후
EXPIRE_AFTER_MINUTES가 지난 active 세션은 내보낼 때 abandoned로 본다. DB 값은 바꾸지 않는다.
"""
import csv
import time

from sqlmodel import Session, select

from .models import Purchase, ShoppingSession, View

COLUMNS = ["session_id", "event", "item_id", "timestamp", "status", "kind", "mode"]
EXPIRE_AFTER_MINUTES = 60


def export_rows(db: Session, now_ms=None):
    """조회·결제 기록을 세션 순서, 시각 순서로 돌려준다."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    sessions = {s.id: s for s in db.exec(select(ShoppingSession)).all()}
    rows = []
    for view in db.exec(select(View).order_by(View.session_id, View.timestamp, View.id)).all():
        rows.append(
            {
                "session_id": view.session_id,
                "event": "view",
                "item_id": view.item_id,
                "timestamp": view.timestamp,
                "kind": "",
            }
        )
    for purchase in db.exec(
        select(Purchase).order_by(Purchase.session_id, Purchase.timestamp, Purchase.id)
    ).all():
        rows.append(
            {
                "session_id": purchase.session_id,
                "event": "purchase",
                "item_id": purchase.item_id,
                "timestamp": purchase.timestamp,
                "kind": purchase.kind,
            }
        )

    last_activity = {}
    for row in rows:
        last_activity[row["session_id"]] = max(row["timestamp"], last_activity.get(row["session_id"], 0))
    expire_before = now_ms - EXPIRE_AFTER_MINUTES * 60_000
    for row in rows:
        session = sessions[row["session_id"]]
        status = session.status
        if status == "active" and last_activity[row["session_id"]] < expire_before:
            status = "abandoned"
        row["status"] = status
        row["mode"] = session.mode

    rows.sort(key=lambda r: (r["session_id"], r["timestamp"], r["event"] != "view"))
    return [{column: row[column] for column in COLUMNS} for row in rows]


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path
