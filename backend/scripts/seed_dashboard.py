"""대시보드 확인용 가상 손님을 실행 중인 서버에 흘려보낸다.

DB에 숫자를 직접 넣지 않고 실제 API(세션 생성 → 조회 → 결제)를 호출하므로,
확률·단계·예상 구매 수가 모두 실제 모델로 계산된다. 추가 패키지 없이 실행된다.

    python backend/scripts/seed_dashboard.py --shoppers 30

조회 시각은 서버가 기록해서, 스크립트로 넣은 손님은 모두 "아주 빠르게 클릭한 손님"이 된다.
테스트 데이터를 지우려면 docker compose down -v 후 다시 실행한다.
"""
import argparse
import json
import random
import urllib.request

CATEGORIES = ["TOP", "BOTTOM", "OUTER", "DRESS", "SHOES", "BAG"]

# 쇼핑 흐름. 글자는 같은 카테고리 안의 서로 다른 상품이다.
# A와 B는 같은 종류의 두 상품(예: TOP-01·02 니트 두 종류)으로 고른다.
PATTERNS = {
    "decided": "ABAAA",  # 한 상품을 반복해서 봄
    "comparing": "ABABAB",  # 비슷한 두 상품을 번갈아 봄
    "browsing": "ABCDEF",  # 여러 상품을 한 번씩 둘러봄
    "leaving": "AAABCDEF",  # 보던 상품에서 멀어짐
}


def call(base_url, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def pick_products(rng, letters):
    """글자마다 같은 카테고리의 상품을 배정한다. A·B는 같은 종류의 두 상품."""
    category = rng.choice(CATEGORIES)
    first = rng.choice([1, 3, 5, 7])
    numbers = [first, first + 1]
    others = [n for n in range(1, 9) if n not in numbers]
    rng.shuffle(others)
    numbers += others
    distinct = sorted(set(letters))
    return {letter: f"{category}-{numbers[k]:02d}" for k, letter in enumerate(distinct)}


def shop(base_url, rng, pattern, purchase_rate):
    session_id = call(base_url, "POST", "/sessions", {})["session_id"]
    products = pick_products(rng, pattern)
    stage = None
    for letter in pattern:
        stage = call(
            base_url, "POST", f"/sessions/{session_id}/views", {"item_id": products[letter]}
        )["stage"]

    # 일부 손님은 마지막 단계의 대상 상품(없으면 A)을 결제하고 떠난다.
    purchased = None
    if rng.random() < purchase_rate:
        purchased = (stage["items"] or [products["A"]])[0]
        call(base_url, "POST", f"/sessions/{session_id}/purchases", {"item_id": purchased})
    return stage["stage"], purchased


def main():
    parser = argparse.ArgumentParser(description="대시보드 확인용 가상 손님 생성")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--shoppers", type=int, default=30)
    parser.add_argument("--purchase-rate", type=float, default=0.3,
                        help="쇼핑 후 결제하고 떠나는 손님 비율. 나머지는 쇼핑 중으로 남는다.")
    parser.add_argument("--seed", type=int, default=None, help="같은 손님 구성을 다시 만들 때 지정")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    names = list(PATTERNS)
    summary = {}
    for _ in range(args.shoppers):
        name = rng.choice(names)
        stage, purchased = shop(args.base_url, rng, PATTERNS[name], args.purchase_rate)
        key = (name, stage, "결제" if purchased else "쇼핑 중")
        summary[key] = summary.get(key, 0) + 1

    print(f"가상 손님 {args.shoppers}명 생성")
    for (name, stage, status), count in sorted(summary.items()):
        print(f"  흐름 {name:<9} → 단계 {stage:<9} {status:<5} {count}명")
    print(f"대시보드: {args.base_url}/dashboard")


if __name__ == "__main__":
    main()
