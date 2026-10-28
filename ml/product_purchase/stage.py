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
"""

STAGE_THRESHOLDS = {
    # 이보다 조회가 적으면 판단하지 않는다 (첫 조회만으로는 상품을 구분하지 못함, AUC 0.5)
    "min_views": 3,
    # 살 마음 먹음: 1위 lift와 1·2위 ratio
    "decided_lift": 3.0,
    "decided_ratio": 2.0,
    # 고민 중: 1·2위가 모두 이 lift 이상이고 ratio가 이보다 작음
    "comparing_lift": 2.0,
    "comparing_ratio": 1.5,
    "comparing_max_items": 3,
    # 떠나려는 중: 이 lift 이상인 관심 상품을 연속으로 이만큼 안 봤고,
    # 비중이 마지막으로 봤을 때의 이 비율 미만으로 떨어짐
    "leaving_lift": 3.0,
    "leaving_absent_views": 3,
    "leaving_share_drop": 0.75,
}


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


def _leaving_item(timeline, now, base_probability, t):
    """관심 상품 중 멀어지는 중인 것. 여러 개면 지금 확률이 가장 높은 것."""
    for item, probability in sorted(now.items(), key=lambda kv: -kv[1]):
        if probability / base_probability < t["leaving_lift"]:
            break
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

    leaving = _leaving_item(timeline, now, base_probability, t)
    if leaving is not None:
        return result("leaving", [leaving])

    lift = metrics["top1_lift"]
    ratio = metrics["top1_top2_ratio"]
    if lift >= t["decided_lift"] and (ratio is None or ratio >= t["decided_ratio"]):
        return result("decided", [ranked[0][0]])

    if (
        ratio is not None
        and ranked[1][1] / base_probability >= t["comparing_lift"]
        and ratio < t["comparing_ratio"]
    ):
        items = [
            item
            for item, probability in ranked[: t["comparing_max_items"]]
            if probability / base_probability >= t["comparing_lift"]
        ]
        return result("comparing", items)

    return result("browsing")
