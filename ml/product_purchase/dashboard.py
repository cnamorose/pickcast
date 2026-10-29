"""판매자 대시보드용 집계 함수. 지금 쇼핑 중인 세션들의 예측을 상품별·단계별로 모은다.

모델을 다시 학습하지 않고, 모델이 내놓은 보정 확률과 단계 판단(stage.py) 결과를 집계한다.
어떤 세션을 "지금 쇼핑 중"으로 볼지는 호출하는 쪽(백엔드)이 정한다.

    forecast_sales({"A": [0.02, 0.05], "B": [0.03]})
    count_stages(["browsing", "comparing", "browsing"])
    compare_pairs([judge_stage(...), judge_stage(...)])

예상 구매 수는 "기간 안에 몇 개"가 아니다. 모델의 정답에 기간 제한이 없어서,
"지금 이 상품을 보고 있는 고객 중 결국 몇 명이 살지"를 뜻한다.
"""
from collections import Counter
from itertools import combinations

STAGES = ["browsing", "comparing", "decided", "leaving"]


def purchase_count_distribution(probabilities):
    """고객마다 구매 확률이 다를 때 구매 수의 분포 (포아송-이항 분포).

    고객을 한 명씩 더하며 "지금까지 k명이 살 확률"을 갱신한다 (DP, O(n²)).
    결과의 k번째 값이 정확히 k명이 살 확률이다.
    """
    distribution = [1.0]
    for p in probabilities:
        updated = [0.0] * (len(distribution) + 1)
        for k, mass in enumerate(distribution):
            updated[k] += mass * (1 - p)
            updated[k + 1] += mass * p
        distribution = updated
    return distribution


def _quantile(distribution, q):
    """누적 확률이 처음으로 q 이상이 되는 구매 수."""
    cumulative = 0.0
    for k, mass in enumerate(distribution):
        cumulative += mass
        if cumulative >= q - 1e-12:
            return k
    return len(distribution) - 1


def forecast_sales(probabilities_by_item, interval=0.9):
    """상품별 예상 구매 수, 범위, 1명 이상 살 확률. 예상 구매 수가 큰 순서로 돌려준다.

    probabilities_by_item: {상품 ID: [쇼핑 중인 고객별 그 상품의 구매 확률, ...]}
    interval: 범위에 담을 확률. 0.9면 하위·상위 5%를 잘라 90% 범위를 낸다.

    확률이 보정돼 있어 합이 실제 구매 수에 가깝다 (test 평균 예측 0.92% = 실제 0.92%).
    고객 수가 적으면 예상 구매 수가 0.1보다 작게 나오므로, 화면에서는 at_least_one이
    더 읽기 쉽다.
    """
    tail = (1 - interval) / 2
    forecasts = []
    for item, probabilities in probabilities_by_item.items():
        distribution = purchase_count_distribution(probabilities)
        forecasts.append(
            {
                "item_id": item,
                "viewers": len(probabilities),
                "expected": float(sum(probabilities)),
                "low": _quantile(distribution, tail),
                "high": _quantile(distribution, 1 - tail),
                "at_least_one": 1 - distribution[0],
            }
        )
    forecasts.sort(key=lambda f: (-f["expected"], str(f["item_id"])))
    return forecasts


def count_stages(stages):
    """단계별 세션 수. 해당 세션이 없는 단계도 0으로 넣는다."""
    counts = Counter(stages)
    return {stage: counts.get(stage, 0) for stage in STAGES} | {
        stage: count for stage, count in counts.items() if stage not in STAGES
    }


def compare_pairs(stage_results, limit=None):
    """고민 중(comparing) 세션들이 비교한 상품 쌍과 그 세션 수. 많은 순서로 돌려준다.

    단순히 같이 본 상품이 아니라, 단계 판단에서 고민 중으로 판정된 세션의 비교 상품만 센다.
    한 세션이 3개를 비교하면 가능한 쌍 3개를 하나씩 센다.
    """
    counts = Counter()
    for result in stage_results:
        if result["stage"] != "comparing":
            continue
        for pair in combinations(sorted(set(result["items"]), key=str), 2):
            counts[pair] += 1
    pairs = sorted(counts.items(), key=lambda kv: (-kv[1], [str(i) for i in kv[0]]))
    if limit is not None:
        pairs = pairs[:limit]
    return [{"items": list(pair), "sessions": count} for pair, count in pairs]
