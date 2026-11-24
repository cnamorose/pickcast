"""시간 단위로 train/valid/test를 나눈다 (이전 기간으로 학습, 이후 기간으로 평가).

모든 기록(조회·장바구니·구매)이 한 구간 안에 있는 사용자만 그 구간에 배정한다.
두 구간 이상에 기록이 걸친 사용자는 excluded로 표시하고 학습·평가에 쓰지 않는다.
한 사용자가 학습과 평가에 함께 들어가지 않고, 정답(이후 구매)도 다른 구간을 보지 않는다.

    train: 2015-05-03 ~ 2015-06-30   학습
    valid: 2015-07-01 ~ 2015-07-31   모델 선택·확률 보정·임계값
    test:  2015-08-01 ~ 2015-09-18   한 번만 평가

사용자 단위 분할(split_users.py)의 결과를 덮어쓰지 않도록 PRODUCT_PURCHASE_DIR을 바꿔 실행한다.

    $env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
    python ml/product_purchase/split_by_time.py
"""
import json

import numpy as np
import pandas as pd

from events import (
    DEFAULT_OUTPUT_NAME,
    HEAVY_USER_MIN_VIEWS,
    first_purchase_times,
    load_events,
    output_dir,
    sorted_views,
)


SPLITS = ["train", "valid", "test", "excluded"]
# 구간 시작 시각 (UTC). 이 시각 이상이면 다음 구간이다.
VALID_START = pd.Timestamp("2015-07-01").value // 1_000_000
TEST_START = pd.Timestamp("2015-08-01").value // 1_000_000


def period_of(timestamp):
    """시각(ms)마다 0=train, 1=valid, 2=test."""
    return (timestamp >= VALID_START).astype(np.int8) + (timestamp >= TEST_START)


def main():
    if output_dir.name == DEFAULT_OUTPUT_NAME:
        raise SystemExit(
            "사용자 단위 분할 결과를 덮어쓰지 않도록 PRODUCT_PURCHASE_DIR을 바꿔 실행하세요."
        )

    print("이벤트를 읽습니다.", flush=True)
    events, _ = load_events()
    views = sorted_views(events)

    users = views.groupby("visitorid").size().rename("n_views").to_frame()
    users["heavy_user"] = (users["n_views"] >= HEAVY_USER_MIN_VIEWS).astype("int8")

    first_view = views.groupby(["visitorid", "itemid"])["timestamp"].min()
    first_buy = first_purchase_times(events)
    both = pd.concat([first_view.rename("view"), first_buy.rename("buy")], axis=1,
                     join="inner")
    buyers = both.index[both["view"] < both["buy"]].get_level_values("visitorid")
    users["is_buyer"] = users.index.isin(buyers).astype("int8")

    # 조회뿐 아니라 장바구니·구매 기록까지 포함해 사용자가 걸친 구간을 본다.
    period = pd.Series(period_of(events["timestamp"].to_numpy()), index=events["visitorid"])
    first_period = period.groupby(level=0).min()
    last_period = period.groupby(level=0).max()
    single = (first_period == last_period).reindex(users.index)
    users["split"] = np.where(single, first_period.reindex(users.index), SPLITS.index("excluded"))
    users["split"] = pd.Categorical.from_codes(users["split"].astype(np.int8), SPLITS)
    users = users.reset_index()

    output_dir.mkdir(parents=True, exist_ok=True)
    users.to_parquet(output_dir / "users.parquet", index=False)

    report = {
        "method": "time",
        "valid_start": "2015-07-01",
        "test_start": "2015-08-01",
        "heavy_user_min_views": HEAVY_USER_MIN_VIEWS,
        "splits": {},
    }
    for name, group in users.groupby("split", observed=True):
        report["splits"][name] = {
            "users": len(group),
            "buyers": int(group["is_buyer"].sum()),
            "heavy_users": int(group["heavy_user"].sum()),
            "heavy_buyers": int((group["heavy_user"] & group["is_buyer"]).sum()),
            "views": int(group["n_views"].sum()),
        }
    (output_dir / "split_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for name, values in report["splits"].items():
        print(
            f"{name}: 사용자 {values['users']:,}명 / 구매 사용자 {values['buyers']:,}명 / "
            f"과다 조회 {values['heavy_users']}명 / 조회 {values['views']:,}건"
        )


if __name__ == "__main__":
    main()
