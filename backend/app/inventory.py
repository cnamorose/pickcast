import random

# 데모용 가상 재고. 실제 쇼핑몰이라면 원래 가진 재고 데이터를 쓴다.
# 상품 ID는 frontend/src/data/products.js와 같아야 한다 (카테고리 6개 × 8개 = 48개).
CATEGORIES = ["TOP", "BOTTOM", "OUTER", "DRESS", "SHOES", "BAG"]
ITEMS_PER_CATEGORY = 8

# 매번 같은 값이 나오도록 시드를 고정한다. 재고가 적은 상품이 섞여 있어야
# 대시보드에서 "재고보다 많이 팔릴 수 있음"을 보여줄 수 있다.
_rng = random.Random(42)

STOCK = {
    f"{category}-{number:02d}": _rng.randint(1, 10)
    for category in CATEGORIES
    for number in range(1, ITEMS_PER_CATEGORY + 1)
}
