from pathlib import Path

import pandas as pd


ml_dir = Path(__file__).resolve().parents[1]
events_path = ml_dir / "data" / "raw" / "events.csv"
output_dir = ml_dir / "data" / "product_purchase"

# 조회 수가 이 값 이상인 사용자를 과다 조회 사용자로 표시한다.
# 삭제하지 않고 표시만 하며, 학습·평가에서 포함/제외 결과를 비교한다.
HEAVY_USER_MIN_VIEWS = 100


def load_events():
    """원본 이벤트를 읽고 완전히 동일한 행을 한 건만 남긴다."""
    events = pd.read_csv(
        events_path,
        usecols=["timestamp", "visitorid", "event", "itemid", "transactionid"],
        dtype={
            "timestamp": "int64",
            "visitorid": "int32",
            "event": "category",
            "itemid": "int32",
            "transactionid": "float64",
        },
    )
    duplicated = events.duplicated()
    duplicate_counts = (
        events.loc[duplicated, "event"].value_counts().astype(int).to_dict()
    )
    events = events.loc[~duplicated].reset_index(drop=True)
    return events, duplicate_counts


def sorted_views(events):
    """사용자별 조회를 시간순으로 정렬한다. 같은 시각의 조회는 원본 순서를 유지한다."""
    views = events.loc[events["event"] == "view", ["visitorid", "timestamp", "itemid"]]
    return views.sort_values(["visitorid", "timestamp"], kind="stable").reset_index(
        drop=True
    )


def first_purchase_times(events):
    """사용자·상품별 첫 구매 시각."""
    purchases = events.loc[events["event"] == "transaction"]
    return purchases.groupby(["visitorid", "itemid"])["timestamp"].min()
