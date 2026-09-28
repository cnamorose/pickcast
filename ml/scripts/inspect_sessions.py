from pathlib import Path

import pandas as pd


def main():
    ml_dir = Path(__file__).resolve().parents[1]
    data_path = ml_dir / "data" / "raw" / "events.csv"

    df = pd.read_csv(
        data_path,
        usecols=["timestamp", "visitorid", "event", "itemid"],
    )

    views = (
        df.loc[df["event"] == "view"]
        .sort_values(["visitorid", "timestamp"], kind="stable")
        .reset_index(drop=True)
    )

    if views.empty:
        print("조회 기록이 없습니다.")
        return

    # 같은 사용자의 직전 조회와 얼마나 떨어져 있는지 계산합니다.
    gaps = views.groupby("visitorid", sort=False)["timestamp"].diff()

    results = []

    for minutes in [10, 30, 60]:
        threshold_ms = minutes * 60 * 1000

        # 사용자의 첫 조회이거나 기준 시간 이상 끊기면 새 세션입니다.
        new_session = gaps.isna() | gaps.ge(threshold_ms)
        session_ids = new_session.cumsum()

        sessions = views.groupby(session_ids, sort=False).agg(
            view_count=("itemid", "size"),
            candidate_count=("itemid", "nunique"),
        )

        total = len(sessions)
        multiple_candidates = int(
            (sessions["candidate_count"] >= 2).sum()
        )

        results.append({
            "공백 기준(분)": minutes,
            "세션 수": total,
            "후보 1개 세션": int(
                (sessions["candidate_count"] == 1).sum()
            ),
            "후보 2개 이상 세션": multiple_candidates,
            "후보 2개 이상 비율": f"{multiple_candidates / total:.2%}",
            "평균 조회 수": round(sessions["view_count"].mean(), 2),
            "평균 후보 수": round(sessions["candidate_count"].mean(), 2),
        })

    print(f"전체 조회 기록: {len(views):,}")
    print(f"조회 사용자 수: {views['visitorid'].nunique():,}")
    print("\n=== 세션 구분 기준별 비교 ===")
    print(pd.DataFrame(results).to_string(index=False))


if __name__ == "__main__":
    main()