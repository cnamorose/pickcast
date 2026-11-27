"""가게 전체 대시보드 재생(시뮬레이션 화면 오른쪽)의 계산: 가정 재고와 알림.

같은 날 재생 파일(ml/results/replay/날짜.json)에서 시간 창만 잘라, 1분마다
쇼핑 중 손님 수, 다음 10분 예상 판매, 곧 팔릴 상품과 각 상품의 재고·알림을 만든다.

재고는 데이터에 없어 가정한 값이다. 상품마다 상품 번호로 정한 1~5개에서 시작하고, 그 시간 창 안에
실제로 팔리면 줄어든다. 판매자가 채우는 동작은 없다(시뮬레이션은 보기만, 채우기는 게임에서).

알림 규칙
- soldout: 남은 재고 0개
- refill: 남은 재고가 REFILL_STOCK개 이하이고, 다음 10분 안에 1개 이상 팔릴 확률이 REFILL_CHANCE 이상
- ok: 그 밖
"""
from bisect import bisect_right

MIN_STOCK, MAX_STOCK = 1, 5
REFILL_STOCK = 2
REFILL_CHANCE = 0.10
STOCK_RULE = (
    f"재고는 데이터에 없어 상품마다 {MIN_STOCK}~{MAX_STOCK}개로 가정했어요. 실제로 팔리면 줄어들어요. "
    f"남은 재고가 {REFILL_STOCK}개 이하인데 10분 안에 팔릴 확률이 {REFILL_CHANCE:.0%} 이상이면 채우라고 알려요."
)


def initial_stock(item):
    """상품 번호로 정한 가정 재고 (같은 상품은 늘 같은 값)."""
    mixed = (int(item) * 2654435761) % 2**32
    return MIN_STOCK + mixed % (MAX_STOCK - MIN_STOCK + 1)


def stock_status(stock_left, at_least_one):
    if stock_left <= 0:
        return "soldout"
    if stock_left <= REFILL_STOCK and at_least_one >= REFILL_CHANCE:
        return "refill"
    return "ok"


def window_store(day, start_minute, minutes):
    """하루치 재생 데이터(replay_api.load_day)에서 [start_minute, start_minute + minutes) 분을 잘라
    가게 전체 대시보드 상태를 만든다. 시각은 시간 창 시작부터의 초·분이다.
    """
    end_minute = start_minute + minutes
    offset = start_minute * 60
    pc = {name: i for i, name in enumerate(day["purchases"]["columns"])}
    sales = [
        {
            "second": round(r[pc["second"]] - offset, 1),
            "item_id": r[pc["item"]],
            "customer": r[pc["customer"]],
            "probability": r[pc["probability"]],
            "rank": r[pc["rank"]],
        }
        for r in day["purchases"]["rows"]
        if offset <= r[pc["second"]] < end_minute * 60
    ]
    sold_at = {}
    for s in sales:
        sold_at.setdefault(s["item_id"], []).append(s["second"])

    def stock_left(item, second):
        return max(0, initial_stock(item) - bisect_right(sold_at.get(item, []), second))

    tc = {name: i for i, name in enumerate(day["snapshots"]["top_item_columns"])}
    top_items = []
    for k in range(minutes):
        now = k * 60
        rows = []
        for r in day["snapshots"]["top_items"][start_minute + k]:
            item, chance = r[tc["item"]], r[tc["at_least_one"]]
            left = stock_left(item, now)
            rows.append([item, r[tc["expected"]], chance, r[tc["customers"]], left, stock_status(left, chance)])
        top_items.append(rows)

    window = slice(start_minute, end_minute)
    return {
        "minutes": minutes,
        "shoppers": day["snapshots"]["shoppers"][window],
        "carting": day["snapshots"]["carting"][window],
        "expected_next_10m": day["snapshots"]["expected_next_10m"][window],
        "actual_known_next_10m": day["actual_known_next_10m"][window],
        "top_items": top_items,
        "top_item_columns": ["item", "expected", "at_least_one", "customers", "stock_left", "status"],
        "sales": sales,
        "initial_stock": {str(item): initial_stock(item) for item in sorted(sold_at)},
        "stock_rule": STOCK_RULE,
    }
