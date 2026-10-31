"""구매 맞히기 게임 문제 만들기 (추가 체험: 사람 vs AI).

RetailRocket test 사용자의 실제 조회 기록을 보여주고, 사람과 AI가 각자 "이 사람이 산 상품"을
고른다. test 사용자는 모델이 학습에서 보지 않았으므로 AI도 처음 보는 기록으로 맞힌다.

문제 기준
- 첫 구매 이전의 조회만 쓴다. 장바구니 기록은 정답을 거의 알려주므로 쓰지 않는다
  (모델도 조회만 쓴다).
- 결제하러 들어간 마지막 조회(마지막 조회가 산 상품이면 그 1개)는 뺀다 (결과 화면과 같은 규칙).
- 산 상품이 남은 조회 안에 있고, 본 상품이 MIN_ITEMS~MAX_ITEMS종류, 조회가 MAX_VIEWS개 이하이며,
  첫 조회부터 마지막 조회까지 MAX_SPAN_MS 이내(한 번의 쇼핑)인 기록만 쓴다.

난이도 (AI 결과와 무관하게 조회 기록만으로 정한다)
- 1점에서 시작해, 산 상품이 혼자 가장 많이 본 상품이 아니면 +1, 본 상품이 HARD_ITEMS종류 이상이면 +1

문제 파일에는 상품 번호, 첫 조회 후 경과 초, 정답, 난이도만 담는다. 사용자 번호는 담지 않는다.
난이도별 AI 1순위 정답률은 만들 때의 모델 버전과 함께 저장한다.

    python ml/product_purchase/guess_game.py
"""
import json
from collections import Counter

import pyarrow.parquet as pq

from events import load_events, ml_dir, output_dir
from predict import PurchasePredictor

MIN_ITEMS = 2
MAX_ITEMS = 6
MAX_VIEWS = 20
MAX_SPAN_MS = 24 * 3_600_000
HARD_ITEMS = 4

PROBLEMS_PATH = ml_dir / "results" / "guess_problems.json"


def difficulty(items, answer):
    """조회한 상품 목록(순서대로)과 정답으로 난이도 1~3을 정한다."""
    counts = Counter(items)
    top = max(counts.values())
    answer_alone_top = counts[answer] == top and sum(1 for c in counts.values() if c == top) == 1
    return 1 + (not answer_alone_top) + (len(counts) >= HARD_ITEMS)


def build_problem(views, answer):
    """첫 구매 전 조회 [(시각 ms, 상품)](시간순)와 산 상품으로 문제를 만든다. 기준에 맞지 않으면 None."""
    views = list(views)
    if views and views[-1][1] == answer:
        views = views[:-1]
    items = [item for _, item in views]
    kinds = set(items)
    if answer not in kinds or not MIN_ITEMS <= len(kinds) <= MAX_ITEMS or len(views) > MAX_VIEWS:
        return None
    start = views[0][0]
    if views[-1][0] - start > MAX_SPAN_MS:
        return None
    return {
        "level": difficulty(items, answer),
        "answer": answer,
        # [첫 조회 후 경과 초, 상품 번호]
        "views": [[round((t - start) / 1000), item] for t, item in views],
    }


def test_problems():
    """test 사용자 중 기준에 맞는 문제 목록. 사용자 번호 순으로 만든다."""
    test_users = pq.read_table(
        output_dir / "training_rows" / "test.parquet", columns=["visitorid"]
    ).column(0).unique().to_pylist()
    events, _ = load_events()
    events = events[events["visitorid"].isin(test_users)]

    buys = events[events["event"] == "transaction"].sort_values(["visitorid", "timestamp"], kind="stable")
    first_buy = buys.groupby("visitorid").first()
    views = events[(events["event"] == "view") & events["visitorid"].isin(first_buy.index)]
    views = views.sort_values(["visitorid", "timestamp"], kind="stable")

    problems = []
    for visitor, group in views.groupby("visitorid", sort=True):
        bought = first_buy.loc[visitor]
        before = group[group["timestamp"] < bought["timestamp"]]
        problem = build_problem(
            zip(before["timestamp"].tolist(), before["itemid"].tolist()), int(bought["itemid"])
        )
        if problem:
            problems.append(problem)
    return problems


def ai_pick(predictor, problem):
    """AI 1순위 상품. 문제의 경과 초를 ms로 되돌려 예측한다."""
    views = [(sec * 1000, item) for sec, item in problem["views"]]
    return predictor.predict(views)["candidates"][0]["item_id"]


def export_problems(predictor=None, path=PROBLEMS_PATH):
    predictor = predictor or PurchasePredictor()
    problems = test_problems()
    accuracy = {}
    for problem in problems:
        hit = ai_pick(predictor, problem) == problem["answer"]
        level = accuracy.setdefault(str(problem["level"]), {"problems": 0, "ai_hits": 0})
        level["problems"] += 1
        level["ai_hits"] += hit
    for level in accuracy.values():
        level["ai_rate"] = round(level["ai_hits"] / level["problems"], 4)

    data = {
        "settings": {
            "model_version": predictor.version,
            "split": "test",
            "min_items": MIN_ITEMS,
            "max_items": MAX_ITEMS,
            "max_views": MAX_VIEWS,
            "max_span_hours": MAX_SPAN_MS // 3_600_000,
            "hard_items": HARD_ITEMS,
        },
        "ai_accuracy": dict(sorted(accuracy.items())),
        "problems": [{"id": k, **p} for k, p in enumerate(problems)],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path, data


def load_problems(path=PROBLEMS_PATH):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    path, data = export_problems()
    print(f"문제 {len(data['problems'])}개 저장: {path}")
    for level, a in data["ai_accuracy"].items():
        print(f"  난이도 {level}: {a['problems']}문제, AI 1순위 정답률 {a['ai_rate']:.1%}")


if __name__ == "__main__":
    main()
