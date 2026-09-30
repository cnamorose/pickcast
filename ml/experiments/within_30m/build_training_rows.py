import csv
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
from tqdm import tqdm
import pandas as pd


SESSION_GAP_MS = 30 * 60 * 1000
LABEL_WINDOW_MS = 30 * 60 * 1000
SAMPLE_SESSIONS = None
RANDOM_SEED = 42


def main():
    ml_dir = Path(__file__).resolve().parents[2]
    df = pd.read_csv(
        ml_dir / "data" / "raw" / "events.csv",
        usecols=["timestamp", "visitorid", "event", "itemid"],
    )
    data_end = int(df["timestamp"].max())

    # 원본 행을 삭제하지 않고, 조회 기록만으로 세션을 나눕니다.
    views = (
        df.loc[df["event"].eq("view")]
        .sort_values(["visitorid", "timestamp"], kind="stable")
        .copy()
    )
    gaps = views.groupby("visitorid")["timestamp"].diff()
    views["session_id"] = (
        gaps.isna() | gaps.ge(SESSION_GAP_MS)
    ).cumsum()

    # 구매 결과를 보지 않고 세션을 선택합니다. 
    all_sessions = views["session_id"].drop_duplicates()

    if SAMPLE_SESSIONS is None:
        selected = all_sessions 
    else:
        selected = all_sessions.sample(
        n=min(SAMPLE_SESSIONS, len(all_sessions)),
        random_state=RANDOM_SEED,
    )

    sample_views = views.loc[views["session_id"].isin(selected)]

    # 구매 정보는 정답 생성과 동일 시각 구매 확인에만 사용합니다.
    purchase_times = defaultdict(list)
    purchase_at = defaultdict(set)

    purchases = df.loc[
        df["event"].eq("transaction"),
        ["visitorid", "itemid", "timestamp"],
    ]
    for visitor, item, timestamp in purchases.itertuples(
        index=False, name=None
    ):
        purchase_times[(visitor, item)].append(timestamp)
        purchase_at[visitor].add(timestamp)

    for timestamps in purchase_times.values():
        timestamps.sort()

    output_dir = ml_dir / "data" / "experiments" / "within_30m" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = (
    "training_rows.csv"
    if SAMPLE_SESSIONS is None
    else "training_rows_sample.csv")
    output_path = output_dir / filename
    temp_path = output_path.with_suffix(".csv.tmp")

    columns = [
        "visitorid",
        "session_id",
        "cutoff_timestamp",
        "label_end_timestamp",
        "itemid",
        "view_count",
        "view_share",
        "seconds_since_first_view",
        "seconds_since_last_view",
        "label",
    ]
    stats = Counter()

    with temp_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for session_id, session in tqdm(
    sample_views.groupby("session_id"),
    total=len(selected),
    desc="학습 데이터 생성",
    unit="session",
):
            visitor = int(session["visitorid"].iloc[0])
            counts = Counter()
            first_view = {}
            last_view = {}
            total_views = 0

            # 同じ時刻ではなく、같은 시각의 조회를 모두 반영한 뒤 한 번 예측합니다.
            for cutoff, batch in session.groupby("timestamp", sort=True):
                cutoff = int(cutoff)
                stats["all_snapshots"] += 1

                for item in batch["itemid"]:
                    item = int(item)
                    counts[item] += 1
                    first_view.setdefault(item, cutoff)
                    last_view[item] = cutoff
                    total_views += 1

                label_end = cutoff + LABEL_WINDOW_MS

                # 제외하는 시점의 조회도 이후 예측의 과거 기록에는 남깁니다.
                if label_end > data_end:
                    stats["excluded_incomplete_window"] += 1
                    continue

                if cutoff in purchase_at.get(visitor, ()):
                    stats["excluded_same_time_purchase"] += 1
                    continue

                stats["snapshots"] += 1
                stats["multi_candidate_snapshots"] += int(len(counts) >= 2)
                positive_candidates = 0

                for item, count in counts.items():
                    timestamps = purchase_times.get((visitor, item), ())

                    # 예측 시점보다 엄격히 뒤에 있는 첫 구매를 찾습니다.
                    next_index = bisect_right(timestamps, cutoff)
                    label = int(
                        next_index < len(timestamps)
                        and timestamps[next_index] <= label_end
                    )

                    writer.writerow({
                        "visitorid": visitor,
                        "session_id": int(session_id),
                        "cutoff_timestamp": cutoff,
                        "label_end_timestamp": label_end,
                        "itemid": item,
                        "view_count": count,
                        "view_share": count / total_views,
                        "seconds_since_first_view": (
                            cutoff - first_view[item]
                        ) / 1000,
                        "seconds_since_last_view": (
                            cutoff - last_view[item]
                        ) / 1000,
                        "label": label,
                    })

                    stats["rows"] += 1
                    stats["positive_rows"] += label
                    positive_candidates += label

                if positive_candidates == 0:
                    stats["all_zero_snapshots"] += 1

    # 생성이 끝난 파일만 최종 파일명으로 저장합니다.
    temp_path.replace(output_path)

    print(f"선택한 세션 수: {len(selected):,}")
    print(f"전체 예측 시점 수: {stats['all_snapshots']:,}")
    print(f"사용한 예측 시점 수: {stats['snapshots']:,}")
    print(
        "후보 2개 이상 예측 시점 수: "
        f"{stats['multi_candidate_snapshots']:,}"
    )
    print(
        "모든 후보의 정답이 0인 예측 시점 수: "
        f"{stats['all_zero_snapshots']:,}"
    )
    print(
        "관찰 기간 부족으로 제외: "
        f"{stats['excluded_incomplete_window']:,}"
    )
    print(
        "동일 시각 구매로 제외: "
        f"{stats['excluded_same_time_purchase']:,}"
    )
    print(f"\n학습용 상품 행 수: {stats['rows']:,}")
    print(f"label=1 행 수: {stats['positive_rows']:,}")
    print(f"label=0 행 수: {stats['rows'] - stats['positive_rows']:,}")
    print(f"\n저장 위치: {output_path}")


if __name__ == "__main__":
    main()
