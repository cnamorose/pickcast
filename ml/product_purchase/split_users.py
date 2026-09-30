"""사용자 단위로 train/valid/test를 나눈다.

과다 조회 여부와 구매 여부로 층을 나누고, 각 층을 조회 수 순으로 정렬한 뒤
20명씩 묶어 14/3/3명을 무작위 배정한다. 조회량이 비슷한 사용자끼리
여러 구간에 고르게 나뉘므로, 소수 과다 조회 사용자가 한 구간에 몰리지 않는다.
"""
import json

import numpy as np
import pandas as pd

from events import (
    HEAVY_USER_MIN_VIEWS,
    first_purchase_times,
    load_events,
    output_dir,
    sorted_views,
)


SEED = 42
SPLITS = ["train", "valid", "test"]
BLOCK = [0] * 14 + [1] * 3 + [2] * 3


def main():
    print("이벤트를 읽습니다.", flush=True)
    events, _ = load_events()
    views = sorted_views(events)

    users = views.groupby("visitorid").size().rename("n_views").to_frame()
    users["heavy_user"] = (users["n_views"] >= HEAVY_USER_MIN_VIEWS).astype("int8")

    # 조회 뒤에 같은 상품을 구매한 적이 있으면 정답 1 행을 가진 사용자다.
    first_view = views.groupby(["visitorid", "itemid"])["timestamp"].min()
    first_buy = first_purchase_times(events)
    both = pd.concat([first_view.rename("view"), first_buy.rename("buy")], axis=1,
                     join="inner")
    buyers = both.index[both["view"] < both["buy"]].get_level_values("visitorid")
    users["is_buyer"] = users.index.isin(buyers).astype("int8")

    rng = np.random.default_rng(SEED)
    users["tiebreak"] = rng.random(len(users))
    users["split"] = -1
    for _, group in users.groupby(["heavy_user", "is_buyer"]):
        ordered = group.sort_values(["n_views", "tiebreak"], ascending=False).index
        labels = np.empty(len(ordered), dtype=np.int8)
        for start in range(0, len(ordered), len(BLOCK)):
            block = rng.permutation(BLOCK)
            end = min(start + len(BLOCK), len(ordered))
            labels[start:end] = block[: end - start]
        users.loc[ordered, "split"] = labels
    users["split"] = pd.Categorical.from_codes(users["split"], SPLITS)
    users = users.drop(columns="tiebreak").reset_index()

    output_dir.mkdir(parents=True, exist_ok=True)
    users.to_parquet(output_dir / "users.parquet", index=False)

    report = {
        "seed": SEED,
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
