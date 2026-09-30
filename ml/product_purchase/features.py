"""조회 기록으로 후보 상품별 피처를 계산한다.

학습 데이터 생성과 서비스 예측에서 같은 클래스를 사용해 피처 계산 방식을 맞춘다.
입력에는 view만 사용하고, 구매 기록은 후보 제외(구매 완료)에만 사용한다.
"""
import numpy as np


FEATURES = [
    "view_count",
    "view_share",
    "seconds_since_first_view",
    "seconds_since_last_view",
    "revisit_count",
    "user_total_views",
    "distinct_items_viewed",
    "is_last_viewed",
]


class UserViewState:
    """한 사용자의 조회 기록을 누적하고, 현재 시점의 상품별 피처를 계산한다.

    timestamp는 밀리초 단위다. 같은 시각의 조회는 add_views에 한 번에 넘긴다.
    """

    def __init__(self, capacity=8):
        self.size = 0
        self.position = {}
        self.items = np.empty(capacity, dtype=np.int64)
        self.view_count = np.empty(capacity, dtype=np.int32)
        self.first_view = np.empty(capacity, dtype=np.int64)
        self.last_view = np.empty(capacity, dtype=np.int64)
        self.revisit_count = np.empty(capacity, dtype=np.int32)
        self.purchased = np.empty(capacity, dtype=bool)
        # 조회하기 전에 구매한 상품. 나중에 조회해도 후보에 넣지 않는다.
        self.purchased_before_view = set()
        self.total_views = 0
        self.last_item = None
        self.latest_timestamp = None

    def _grow(self):
        capacity = len(self.items) * 2
        for name in (
            "items",
            "view_count",
            "first_view",
            "last_view",
            "revisit_count",
            "purchased",
        ):
            old = getattr(self, name)
            new = np.empty(capacity, dtype=old.dtype)
            new[: self.size] = old[: self.size]
            setattr(self, name, new)

    def add_views(self, timestamp, itemids):
        """같은 시각에 발생한 조회를 순서대로 반영한다."""
        for item in itemids:
            pos = self.position.get(item)
            if pos is None:
                if self.size == len(self.items):
                    self._grow()
                pos = self.size
                self.position[item] = pos
                self.items[pos] = item
                self.view_count[pos] = 1
                self.first_view[pos] = timestamp
                self.revisit_count[pos] = 0
                self.purchased[pos] = item in self.purchased_before_view
                self.size += 1
            else:
                # 다른 상품을 본 뒤 다시 돌아온 조회만 재방문으로 센다.
                if self.last_item != item:
                    self.revisit_count[pos] += 1
                self.view_count[pos] += 1
            self.last_view[pos] = timestamp
            self.last_item = item
            self.total_views += 1
        self.latest_timestamp = timestamp

    def mark_purchased(self, itemid):
        """구매한 상품을 이후 예측 대상에서 제외한다. 다른 상품의 기록은 유지한다."""
        pos = self.position.get(itemid)
        if pos is None:
            self.purchased_before_view.add(itemid)
        else:
            self.purchased[pos] = True

    def candidates(self):
        """아직 구매하지 않은 조회 상품의 위치."""
        return np.flatnonzero(~self.purchased[: self.size])

    def features(self, now, positions):
        """now 시점의 피처를 positions 순서대로 계산한다."""
        view_count = self.view_count[positions]
        last_view = self.last_view[positions]
        return {
            "view_count": view_count,
            "view_share": (view_count / self.total_views).astype(np.float32),
            "seconds_since_first_view": (
                (now - self.first_view[positions]) / 1000
            ).astype(np.float32),
            "seconds_since_last_view": ((now - last_view) / 1000).astype(np.float32),
            "revisit_count": self.revisit_count[positions],
            "user_total_views": np.full(
                len(positions), self.total_views, dtype=np.int32
            ),
            "distinct_items_viewed": np.full(
                len(positions), self.size, dtype=np.int32
            ),
            # 같은 시각에 여러 상품을 봤다면 모두 가장 최근 조회로 본다.
            "is_last_viewed": (last_view == self.latest_timestamp).astype(np.int8),
        }
