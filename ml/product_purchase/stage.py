"""확률 흐름으로 고객의 구매 의도 단계를 판단한다. 사용자 맞춤 화면용이다.

predictor.timeline()의 결과(조회 시점마다 후보별 확률)를 받아 지금 단계를 돌려준다.
모델을 다시 학습하지 않고, 모델이 내놓은 확률 위에 규칙만 얹는다.

    stage = judge_stage(predictor.timeline(views), predictor.base_probability)
    # {"stage": "comparing", "items": ["A", "C"], "metrics": {...}}

단계는 4가지다.

    browsing   구경 중       눈에 띄게 높은 상품이 없음 → 다양한 상품 추천
    comparing  고민 중       상위 2~3개가 비슷하게 높음 → 비교 카드
    decided    살 마음 먹음  1위가 높고 2위와 차이가 큼 → 팝업·추천 끄기, 구매 버튼 강조
    leaving    떠나려는 중   관심 상품에서 멀어지는 중 → 찜, 가격 알림 유도

valid 검증 결과(docs/ml/stage-validation.md), 그 뒤 실제 구매율은 구경 중 < 살 마음 먹음 <
고민 중 순이다. "살 마음 먹음"은 가장 높은 구매 의도가 아니라 한 상품에 관심이 집중된 상태로
해석한다. 실제 구매로 가장 많이 이어지는 단계는 고민 중이다.

확률의 약 70%가 0.5~1%에 몰려 있어 절대값 대신 상대값으로 판단한다.
- lift: 기준 확률(상품을 한 번만 봤을 때의 확률, 약 0.55%) 대비 배수
- ratio: 1위 확률 ÷ 2위 확률
- share: 그 상품 확률 ÷ 전체 후보 확률 합

기획서와 달라진 점: "떠나려는 중"은 원래 1위 확률이 꺾여 떨어지는 것으로 판단하려 했다.
그러나 이 모델은 첫 조회 후 시간이 지날수록 확률이 오르게 학습돼서, 체험 시간(수십 분)
안에는 1위 확률이 떨어지지 않는다. 예를 들어 A를 3번 본 뒤 다른 상품 7개를 보면
A의 lift는 4.1배 → 8.2배로 오히려 오르고, 아무것도 안 해도 5분 뒤 8.7배, 3시간 뒤
4.2배로 몇 시간이 지나야 떨어진다. 반면 비중(share)은 다른 상품을 볼수록
100% → 62% → 49% → 37%로 떨어지므로, 확률 값 대신 비중의 하락으로 판단한다.

기준값(STAGE_THRESHOLDS)은 손으로 만든 조회 시나리오를 보고 정한 임시값이다.
valid 데이터로 확정한 뒤 test로 한 번 확인한다.

클릭 간격에 따라 확률이 달라진다. 첫 조회 후 경과 시간 피처 때문에 같은 상품을
반복해서 봐도 빠르게 누르면 덜 오른다 (A B A A A: 30초 간격 4.15배, 1~5초 간격 2.52배).
또 방금 본 상품은 한 번만 봐도 2.24배가 나와서, 빠르게 누를 때는 lift와 ratio만으로
"모두 다른 상품을 본 경우"(2.24배, ratio 2.18)와 "같은 상품을 반복한 경우"(2.52배,
ratio 2.27)를 가르기 어렵다. 그래서 살 마음 먹음에 1위 비중 조건을 더했다. 반복한
경우 1위 비중은 66~74%, 모두 다른 상품을 본 경우는 30% 안팎이다.

같은 이유로 한 번만 본 상품은 단계 판단 대상에서 뺀다. 관심 상품이 있는 상태에서 새 상품을
한 번 열기만 해도 그 상품이 약 2.2배가 되어, 빼지 않으면 A A B 같은 흐름이 "A와 B를
고민 중"으로 판정된다. 맞춤 화면에서는 모달을 잘못 띄우는 쪽이 놓치는 쪽보다 나쁘므로,
애매하면 구경 중으로 둔다.
"""
from collections import Counter


STAGE_THRESHOLDS = {
    # 이보다 조회가 적으면 판단하지 않는다 (첫 조회만으로는 상품을 구분하지 못함, AUC 0.5)
    "min_views": 3,
    # 이보다 적게 본 상품은 고민 중·살 마음 먹음·떠나려는 중의 대상이 되지 않는다
    "min_item_views": 2,
    # 살 마음 먹음: 1위 lift, 1·2위 ratio, 1위 비중
    # ratio는 v2(일반 고객 재보정)에서 A B A A A·20초 간격이 1.77배로 1.8에 못 미쳐 1.7로 낮췄다.
    # valid 검증에서 1.5~2.0 사이는 살 마음 먹음 구매율이 거의 같았다 (docs/ml/stage-validation.md).
    "decided_lift": 2.0,
    "decided_ratio": 1.7,
    "decided_share": 0.5,
    # 고민 중: 1·2위가 모두 이 lift 이상이고 ratio가 이보다 작음
    "comparing_lift": 1.8,
    "comparing_ratio": 1.5,
    "comparing_max_items": 3,
    # 떠나려는 중: 이 lift 이상인 관심 상품을 연속으로 이만큼 안 봤고,
    # 비중이 마지막으로 봤을 때의 이 비율 미만으로 떨어짐
    "leaving_lift": 2.0,
    "leaving_absent_views": 3,
    "leaving_share_drop": 0.75,
}


# 모델 버전이 바뀌어도 의도한 단계가 나와야 하는 대표 흐름. 클릭 간격(초)마다 확인한다.
# 테스트(tests/test_stage.py)와 재학습 파이프라인의 등록 기준(pipeline.py)이 함께 쓴다.
STAGE_SCENARIOS = {
    "ABCDEF": "browsing",  # 여러 상품을 한 번씩 둘러봄
    "ABAAA": "decided",  # 한 상품을 반복해서 봄
    "ABABAB": "comparing",  # 두 상품을 번갈아 봄
    "AAABCDEF": "leaving",  # 보던 상품에서 멀어짐
}
SCENARIO_GAPS_SECONDS = [1, 5, 10, 20, 30]


def scenario_mismatches(predictor, thresholds=None):
    """대표 흐름 중 의도한 단계가 나오지 않는 (흐름, 간격, 나온 단계) 목록."""
    thresholds = thresholds or STAGE_THRESHOLDS
    mismatches = []
    for items, expected in STAGE_SCENARIOS.items():
        for seconds in SCENARIO_GAPS_SECONDS:
            views = [(k * seconds * 1000, item) for k, item in enumerate(items)]
            stage = judge_stage(predictor.timeline(views), predictor.base_probability, thresholds)["stage"]
            if stage != expected:
                mismatches.append((items, seconds, stage))
    return mismatches


def _share(probabilities, item):
    total = sum(probabilities.values())
    return probabilities[item] / total if total > 0 else 0.0


def _views_since(timeline, item):
    """마지막으로 item을 본 뒤의 조회 수와 그 시점의 확률들. 본 적 없으면 (None, None)."""
    count = 0
    for snapshot in reversed(timeline):
        if item in snapshot["viewed"]:
            return count, snapshot["probabilities"]
        count += len(snapshot["viewed"])
    return None, None


def _leaving_item(timeline, now, base_probability, view_counts, t):
    """관심 상품 중 멀어지는 중인 것. 여러 개면 지금 확률이 가장 높은 것."""
    for item, probability in sorted(now.items(), key=lambda kv: -kv[1]):
        if probability / base_probability < t["leaving_lift"]:
            break
        if view_counts[item] < t["min_item_views"]:
            continue
        absent, then = _views_since(timeline, item)
        if absent is None or absent < t["leaving_absent_views"]:
            continue
        if _share(now, item) < _share(then, item) * t["leaving_share_drop"]:
            return item
    return None


def judge_stage(timeline, base_probability, thresholds=STAGE_THRESHOLDS):
    """timeline의 마지막 시점 기준으로 단계를 판단한다.

    판단 순서: 조회 부족 → 떠나려는 중 → 살 마음 먹음 → 고민 중 → 구경 중.
    떠나려는 중을 먼저 본다. 다른 상품만 보는 동안에도 관심 상품의 확률이 올라
    살 마음 먹음 조건을 만족할 수 있기 때문이다.
    """
    t = thresholds
    now = timeline[-1]["probabilities"] if timeline else {}
    ranked = sorted(now.items(), key=lambda kv: -kv[1])
    total_views = sum(len(snapshot["viewed"]) for snapshot in timeline)

    metrics = {"top1_lift": None, "top1_top2_ratio": None, "top1_share": None}
    if ranked:
        top1 = ranked[0][1]
        metrics["top1_lift"] = top1 / base_probability
        metrics["top1_share"] = _share(now, ranked[0][0])
        if len(ranked) > 1 and ranked[1][1] > 0:
            metrics["top1_top2_ratio"] = top1 / ranked[1][1]

    def result(stage, items=()):
        return {"stage": stage, "items": list(items), "metrics": metrics}

    if total_views < t["min_views"] or not ranked:
        return result("browsing")

    view_counts = Counter(item for snapshot in timeline for item in snapshot["viewed"])

    leaving = _leaving_item(timeline, now, base_probability, view_counts, t)
    if leaving is not None:
        return result("leaving", [leaving])

    lift = metrics["top1_lift"]
    ratio = metrics["top1_top2_ratio"]
    if (
        view_counts[ranked[0][0]] >= t["min_item_views"]
        and lift >= t["decided_lift"]
        and (ratio is None or ratio >= t["decided_ratio"])
        and metrics["top1_share"] >= t["decided_share"]
    ):
        return result("decided", [ranked[0][0]])

    # 고민 중은 여러 번 본 상품끼리만 비교한다
    interested = [
        (item, probability)
        for item, probability in ranked
        if view_counts[item] >= t["min_item_views"]
        and probability / base_probability >= t["comparing_lift"]
    ]
    if len(interested) >= 2 and interested[0][1] / interested[1][1] < t["comparing_ratio"]:
        items = [item for item, _ in interested[: t["comparing_max_items"]]]
        return result("comparing", items)

    return result("browsing")
