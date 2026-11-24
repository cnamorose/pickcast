"""조회·장바구니 기록으로 후보 상품별 확장 피처를 계산한다 (판매자용 모델 실험).

기존 features.py는 조회만 쓰고 서비스 모델(v1·v2)이 사용하므로 그대로 둔다. 여기서는
장바구니 담기도 예측 시점으로 보고, 조회하지 않고 담은 상품도 후보에 넣는다.
구매 기록은 후보 제외(구매 완료)와 과거 구매 수에만 사용한다.

피처 묶음
- view: 기존 조회 피처 8개 (조회한 상품은 features.py와 같은 값, 담기만 한 상품은 비어 있음)
- cart: 상품을 담은 횟수, 마지막으로 담은 뒤 경과 시간, 고객이 담은 상품 수
- item: train 기간(5~6월) 상품 통계. item_stats.py가 채운다
- context: 시각, 요일, 방문 횟수, 이전 방문 이후 경과 시간, 이번 방문의 조회 수
- history: 예측 시점 이전에 구매한 상품 수
"""
import numpy as np

from features import FEATURES


# 마지막 조회·담기 뒤 이 시간보다 오래 쉬면 새 방문으로 본다.
SESSION_GAP_MS = 30 * 60_000

FEATURE_GROUPS = {
    "view": FEATURES,
    "cart": ["cart_count", "seconds_since_last_cart", "user_carted_items"],
    "item": ["item_viewers", "item_purchase_rate", "item_cart_rate"],
    "context": [
        "hour",
        "weekday",
        "session_count",
        "seconds_since_prev_session",
        "session_views",
    ],
    "history": ["prior_purchases"],
}
ALL_FEATURES = [name for group in FEATURE_GROUPS.values() for name in group]

# 묶음을 하나씩 더하는 실험과, 전체에서 하나씩 빼는 실험. view는 항상 넣는다.
EXPERIMENTS = {
    "view": ["view"],
    "view_cart": ["view", "cart"],
    "view_cart_item": ["view", "cart", "item"],
    "all": ["view", "cart", "item", "context", "history"],
    "all_minus_cart": ["view", "item", "context", "history"],
    "all_minus_item": ["view", "cart", "context", "history"],
    "all_minus_context": ["view", "cart", "item", "history"],
    "all_minus_history": ["view", "cart", "item", "context"],
}


def experiment_features(name):
    return [feature for group in EXPERIMENTS[name] for feature in FEATURE_GROUPS[group]]


class UserEventState:
    """한 사용자의 조회·장바구니 기록을 누적하고, 현재 시점의 상품별 피처를 계산한다.

    timestamp는 밀리초 단위다. 같은 시각의 조회와 담기는 add_events에 한 번에 넘긴다.
    """

    ITEM_ARRAYS = {
        "items": np.int64,
        "view_count": np.int32,
        "first_view": np.int64,
        "last_view": np.int64,
        "revisit_count": np.int32,
        "cart_count": np.int32,
        "last_cart": np.int64,
        "purchased": bool,
    }

    def __init__(self, capacity=8):
        self.size = 0
        self.position = {}
        for name, dtype in self.ITEM_ARRAYS.items():
            setattr(self, name, np.empty(capacity, dtype=dtype))
        self.purchased_before_touch = set()
        self.total_views = 0
        self.viewed_items = 0
        self.carted_items = 0
        self.last_item = None
        self.latest_view = None
        self.latest_event = None
        self.session_count = 0
        self.prev_session_end = None
        self.session_views = 0
        self.prior_purchases = 0

    def _position(self, item):
        pos = self.position.get(item)
        if pos is not None:
            return pos
        if self.size == len(self.items):
            for name in self.ITEM_ARRAYS:
                old = getattr(self, name)
                new = np.empty(len(old) * 2, dtype=old.dtype)
                new[: self.size] = old[: self.size]
                setattr(self, name, new)
        pos = self.size
        self.position[item] = pos
        self.items[pos] = item
        self.view_count[pos] = 0
        self.first_view[pos] = -1
        self.last_view[pos] = -1
        self.revisit_count[pos] = 0
        self.cart_count[pos] = 0
        self.last_cart[pos] = -1
        self.purchased[pos] = item in self.purchased_before_touch
        self.size += 1
        return pos

    def add_events(self, timestamp, view_items, cart_items):
        """같은 시각의 조회와 담기를 반영한다. 조회는 features.py와 같은 순서 규칙을 따른다."""
        if self.latest_event is None:
            self.session_count = 1
        elif timestamp - self.latest_event > SESSION_GAP_MS:
            self.prev_session_end = self.latest_event
            self.session_count += 1
            self.session_views = 0
        self.latest_event = timestamp

        for item in view_items:
            pos = self._position(item)
            if self.view_count[pos] == 0:
                self.first_view[pos] = timestamp
                self.viewed_items += 1
            elif self.last_item != item:
                # 다른 상품을 본 뒤 다시 돌아온 조회만 재방문으로 센다.
                self.revisit_count[pos] += 1
            self.view_count[pos] += 1
            self.last_view[pos] = timestamp
            self.last_item = item
            self.total_views += 1
            self.session_views += 1
        if view_items:
            self.latest_view = timestamp

        for item in cart_items:
            pos = self._position(item)
            if self.cart_count[pos] == 0:
                self.carted_items += 1
            self.cart_count[pos] += 1
            self.last_cart[pos] = timestamp

    def mark_purchased(self, itemid):
        """구매한 상품을 이후 예측 대상에서 빼고 과거 구매 수를 늘린다."""
        self.prior_purchases += 1
        pos = self.position.get(itemid)
        if pos is None:
            self.purchased_before_touch.add(itemid)
        else:
            self.purchased[pos] = True

    def candidates(self):
        """아직 구매하지 않은, 조회했거나 담은 상품의 위치."""
        return np.flatnonzero(~self.purchased[: self.size])

    def touched_now(self, now, positions):
        """now 시각에 조회했거나 담은 상품인지 (결제하러 들어간 조회를 가리는 데 쓴다)."""
        return (
            (self.last_view[positions] == now) | (self.last_cart[positions] == now)
        ).astype(np.int8)

    def features(self, now, positions):
        """now 시점의 피처를 positions 순서대로 계산한다. item 묶음은 포함하지 않는다."""
        count = len(positions)
        view_count = self.view_count[positions]
        viewed = view_count > 0
        first_view = self.first_view[positions]
        last_view = self.last_view[positions]
        cart_count = self.cart_count[positions]
        last_cart = self.last_cart[positions]
        moment = np.datetime64(int(now), "ms")
        day = moment.astype("datetime64[D]")

        def elapsed(since, present):
            return np.where(present, (now - since) / 1000, np.nan).astype(np.float32)

        return {
            "view_count": view_count,
            "view_share": (
                view_count / self.total_views if self.total_views else np.zeros(count)
            ).astype(np.float32),
            "seconds_since_first_view": elapsed(first_view, viewed),
            "seconds_since_last_view": elapsed(last_view, viewed),
            "revisit_count": self.revisit_count[positions],
            "user_total_views": np.full(count, self.total_views, dtype=np.int32),
            "distinct_items_viewed": np.full(count, self.viewed_items, dtype=np.int32),
            "is_last_viewed": (viewed & (last_view == self.latest_view)).astype(np.int8),
            "cart_count": cart_count,
            "seconds_since_last_cart": elapsed(last_cart, cart_count > 0),
            "user_carted_items": np.full(count, self.carted_items, dtype=np.int32),
            "hour": np.full(count, (moment - day).astype("timedelta64[h]").astype(int), dtype=np.int8),
            # 1970-01-01은 목요일이므로 3을 더해 월요일 0 ~ 일요일 6으로 맞춘다.
            "weekday": np.full(count, (day.astype(int) + 3) % 7, dtype=np.int8),
            "session_count": np.full(count, self.session_count, dtype=np.int32),
            "seconds_since_prev_session": np.full(
                count,
                np.nan if self.prev_session_end is None else (now - self.prev_session_end) / 1000,
                dtype=np.float32,
            ),
            "session_views": np.full(count, self.session_views, dtype=np.int32),
            "prior_purchases": np.full(count, self.prior_purchases, dtype=np.int32),
        }
