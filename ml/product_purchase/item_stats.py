"""train 기간(2015-05-03 ~ 06-30) 기록으로 상품 통계를 계산한다.

- item_viewers: 상품을 조회한 사람 수
- item_purchase_rate: 조회한 사람 대비 구매한 사람 비율
- item_cart_rate: 조회한 사람 대비 담은 사람 비율

비율은 사람이 적은 상품이 튀지 않도록 전체 비율 쪽으로 당긴다 (PRIOR_WEIGHT명을 더 본 것처럼).
train 기간에 없던 상품은 조회 0명, 비율은 전체 비율이 된다.

valid·test 행은 train 기간 전체 통계를 쓴다. train 행은 자기 정답이 통계에 섞이지 않도록
train 사용자를 FOLDS개 묶음(visitorid % FOLDS)으로 나눠, 자기 묶음을 뺀 통계를 쓴다.
"""
import numpy as np
import pandas as pd

from split_by_time import VALID_START


FOLDS = 5
PRIOR_WEIGHT = 20
COLUMNS = ["item_viewers", "item_purchase_rate", "item_cart_rate"]
OTHER = -1


def user_group(visitorid, split):
    """train 사용자는 묶음 번호, 그 외(구간에 걸친 사용자 등)는 OTHER."""
    return np.where(split == "train", visitorid % FOLDS, OTHER)


def compute(events, users):
    """상품 통계 표를 만든다. index는 (fold, itemid)이고 fold=OTHER가 전체 통계다."""
    past = events.loc[events["timestamp"] < VALID_START, ["visitorid", "event", "itemid"]]
    split = past["visitorid"].map(users.set_index("visitorid")["split"].astype(str))
    past = past.assign(group=user_group(past["visitorid"].to_numpy(), split.to_numpy()))

    # 묶음끼리 사용자가 겹치지 않으므로, 묶음별 사람 수를 더하고 빼서 통계를 만든다.
    counts = (
        past.drop_duplicates(["visitorid", "event", "itemid"])
        .groupby(["group", "itemid", "event"], observed=True)
        .size()
        .unstack("event", fill_value=0)
        .reindex(columns=["view", "addtocart", "transaction"], fill_value=0)
    )
    total = counts.groupby(level="itemid").sum()
    prior_purchase = total["transaction"].sum() / total["view"].sum()
    prior_cart = total["addtocart"].sum() / total["view"].sum()

    def stats(table):
        return pd.DataFrame(
            {
                "item_viewers": table["view"].astype(np.float32),
                "item_purchase_rate": (
                    (table["transaction"] + PRIOR_WEIGHT * prior_purchase)
                    / (table["view"] + PRIOR_WEIGHT)
                ).astype(np.float32),
                "item_cart_rate": (
                    (table["addtocart"] + PRIOR_WEIGHT * prior_cart)
                    / (table["view"] + PRIOR_WEIGHT)
                ).astype(np.float32),
            }
        )

    tables = {OTHER: stats(total)}
    for fold in range(FOLDS):
        if fold in counts.index.get_level_values("group"):
            own = counts.xs(fold, level="group").reindex(total.index, fill_value=0)
        else:
            own = 0
        tables[fold] = stats(total - own)
    table = pd.concat(tables, names=["fold", "itemid"])
    defaults = {
        "item_viewers": np.float32(0),
        "item_purchase_rate": np.float32(prior_purchase),
        "item_cart_rate": np.float32(prior_cart),
    }
    return table, defaults


def attach(frame, split_name, table, defaults):
    """행에 상품 통계를 붙인다. train 행은 자기 묶음을 뺀 통계를 쓴다."""
    if split_name == "train":
        fold = frame["visitorid"].to_numpy() % FOLDS
    else:
        fold = np.full(len(frame), OTHER)
    keys = pd.MultiIndex.from_arrays([fold, frame["itemid"].to_numpy()], names=["fold", "itemid"])
    values = table.reindex(keys)
    for name in COLUMNS:
        frame[name] = values[name].fillna(defaults[name]).to_numpy(dtype=np.float32)
    return frame
