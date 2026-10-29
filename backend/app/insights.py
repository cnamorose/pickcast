"""판매자 대시보드의 규칙 기반 안내 문장. 대시보드 숫자 중 확인해볼 만한 것을 골라 문장으로 만든다.

LLM 대신 규칙으로 만든다. 조건에 맞을 때만 정해진 문장이 나와서 근거 없는 말을 하지 않고,
테스트할 수 있으며, 비용·지연·네트워크 문제가 없다. 원인(가격, 사진 등)은 데이터에 없어서
추측하지 않고 "확인해볼 점"으로만 쓴다.

    insights = dashboard_insights(active_sessions, products, stage_results, pairs)
    # [{"type": "low_stock", "items": ["OUTER-03"], "message": "..."}, ...]

products는 /dashboard 응답의 products(forecast_sales 결과에 purchased, stock을 붙인 것),
stage_results는 쇼핑 중 세션들의 judge_stage 결과, pairs는 compare_pairs 결과다.

모델 출력으로 계산하는 집계(ml/product_purchase/dashboard.py)와 달리, 재고·결제 수를 보고
판매자에게 하는 운영 안내라서 백엔드에 둔다.
"""
from collections import Counter

INSIGHT_THRESHOLDS = {
    # 쇼핑 중 고객이 이보다 적으면 행동 기반 안내는 하지 않는다 (몇 명의 행동으로 판단하기 이름)
    "min_active_sessions": 5,
    # 남은 재고(재고 - 결제 수)가 이 값 이하이고 지금 보는 고객이 있으면 재고 부족
    "low_stock_remaining": 1,
    # 같은 상품 쌍을 고민 중인 세션이 이 수 이상이면 함께 고민 안내
    "compare_sessions": 2,
    # 본 고객이 이 수 이상인데 살 마음 먹은 고객이 없으면 관심 대비 의도 약함
    "weak_intent_viewers": 3,
    # 같은 상품에서 멀어지는 세션이 이 수 이상이면 이탈 안내
    "leaving_sessions": 2,
}
INSIGHT_LIMIT = 5
# 한 종류가 자리를 다 차지하지 않도록 종류별 최대 개수를 둔다
# (재고가 적은 상품이 많으면 재고 안내만 5개가 나와 다른 안내가 가려진다)
INSIGHT_PER_TYPE = 2


def _insight(kind, items, message):
    return {"type": kind, "items": list(items), "message": message}


def _stock_insights(products, t):
    """재고가 모두 팔렸거나 지금 보는 고객에 비해 남은 재고가 적은 상품. 남은 재고가 적은 순."""
    found = []
    for product in products:
        if product.get("stock") is None or product["viewers"] == 0:
            continue
        remaining = product["stock"] - product["purchased"]
        item = product["item_id"]
        if remaining <= 0:
            message = (
                f"{item}은(는) 재고가 모두 팔렸는데 지금 {product['viewers']}명이 보고 있습니다."
                " 재입고나 대체 상품 안내를 확인해 보세요."
            )
        elif remaining <= max(product["high"], t["low_stock_remaining"]):
            message = (
                f"{item}은(는) 남은 재고 {remaining}개인데 지금 {product['viewers']}명이 보고 있습니다."
                " 재고를 확인해 보세요."
            )
        else:
            continue
        found.append((remaining, -product["viewers"], item, _insight("low_stock", [item], message)))
    return [insight for *_, insight in sorted(found)]


def _compare_insights(pairs, t):
    return [
        _insight(
            "comparing_pair",
            pair["items"],
            f"{pair['items'][0]}과(와) {pair['items'][1]}을(를) 함께 고민 중인 고객이 "
            f"{pair['sessions']}명입니다. 두 상품의 차이를 보여주는 정보를 확인해 보세요.",
        )
        for pair in pairs
        if pair["sessions"] >= t["compare_sessions"]
    ]


def _weak_intent_insights(products, stage_results, t):
    decided = Counter(
        item for result in stage_results if result["stage"] == "decided" for item in result["items"]
    )
    candidates = sorted(
        (p for p in products if p["viewers"] >= t["weak_intent_viewers"] and decided[p["item_id"]] == 0),
        key=lambda p: (-p["viewers"], p["item_id"]),
    )
    return [
        _insight(
            "weak_intent",
            [p["item_id"]],
            f"{p['item_id']}은(는) {p['viewers']}명이 봤지만 구매 의도가 뚜렷한 고객은 아직 없습니다.",
        )
        for p in candidates
    ]


def _leaving_insights(stage_results, t):
    leaving = Counter(
        item for result in stage_results if result["stage"] == "leaving" for item in result["items"]
    )
    return [
        _insight(
            "leaving",
            [item],
            f"{item}을(를) 보다가 다른 상품으로 옮겨가는 고객이 {count}명입니다."
            " 찜·가격 알림 안내를 확인해 보세요.",
        )
        for item, count in sorted(leaving.items(), key=lambda kv: (-kv[1], kv[0]))
        if count >= t["leaving_sessions"]
    ]


def dashboard_insights(
    active_sessions,
    products,
    stage_results,
    pairs,
    thresholds=INSIGHT_THRESHOLDS,
    limit=INSIGHT_LIMIT,
    per_type=INSIGHT_PER_TYPE,
):
    """확인해볼 만한 순서로 안내 문장을 종류별 최대 per_type개, 전체 최대 limit개 돌려준다.

    순서: 재고 → 함께 고민 → 관심 대비 의도 약함 → 이탈.
    재고는 사실에 가까워 고객이 적어도 보여주고, 나머지 행동 기반 안내는
    쇼핑 중 고객이 충분할 때만 보여준다.
    """
    t = thresholds
    groups = [_stock_insights(products, t)]
    if active_sessions < t["min_active_sessions"]:
        notice = _insight(
            "too_few_sessions",
            [],
            f"지금 쇼핑 중인 고객이 {active_sessions}명이라 고객 행동으로 판단하기는 이릅니다.",
        )
        groups.insert(0, [notice])
    else:
        groups += [
            _compare_insights(pairs, t),
            _weak_intent_insights(products, stage_results, t),
            _leaving_insights(stage_results, t),
        ]
    return [insight for group in groups for insight in group[:per_type]][:limit]
