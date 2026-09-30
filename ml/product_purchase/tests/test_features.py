"""features.py의 피처 정의를 손으로 만든 작은 조회 기록으로 확인한다.

학습 데이터 생성과 서비스 예측이 같은 코드를 쓰므로, 정의가 바뀌면 여기서 드러나야 한다.
"""
import unittest

import numpy as np

from features import FEATURES, UserViewState


MINUTE = 60_000
A, B, C = 1, 2, 3


def features_by_item(state, now):
    positions = state.candidates()
    values = state.features(now, positions)
    return {
        int(state.items[pos]): {name: values[name][k] for name in FEATURES}
        for k, pos in enumerate(positions)
    }


class UserViewStateTest(unittest.TestCase):
    def test_first_view(self):
        state = UserViewState()
        state.add_views(0, [A])
        a = features_by_item(state, 0)[A]
        self.assertEqual(a["view_count"], 1)
        self.assertEqual(a["view_share"], 1.0)
        self.assertEqual(a["seconds_since_first_view"], 0)
        self.assertEqual(a["seconds_since_last_view"], 0)
        self.assertEqual(a["revisit_count"], 0)
        self.assertEqual(a["user_total_views"], 1)
        self.assertEqual(a["distinct_items_viewed"], 1)
        self.assertEqual(a["is_last_viewed"], 1)

    def test_revisit_after_other_item(self):
        # A → B → A: A는 다른 상품을 본 뒤 돌아왔으므로 재방문 1회
        state = UserViewState()
        state.add_views(0, [A])
        state.add_views(1 * MINUTE, [B])
        state.add_views(3 * MINUTE, [A])
        features = features_by_item(state, 3 * MINUTE)
        self.assertEqual(features[A]["view_count"], 2)
        self.assertEqual(features[A]["revisit_count"], 1)
        self.assertEqual(features[B]["revisit_count"], 0)
        self.assertAlmostEqual(features[A]["view_share"], 2 / 3, places=6)
        self.assertEqual(features[A]["seconds_since_first_view"], 180)
        self.assertEqual(features[A]["seconds_since_last_view"], 0)
        self.assertEqual(features[B]["seconds_since_last_view"], 120)
        self.assertEqual(features[A]["is_last_viewed"], 1)
        self.assertEqual(features[B]["is_last_viewed"], 0)
        self.assertEqual(features[B]["user_total_views"], 3)
        self.assertEqual(features[B]["distinct_items_viewed"], 2)

    def test_consecutive_views_are_not_revisits(self):
        # A → A: 같은 상품을 연달아 본 것은 재방문이 아니다
        state = UserViewState()
        state.add_views(0, [A])
        state.add_views(MINUTE, [A])
        a = features_by_item(state, MINUTE)[A]
        self.assertEqual(a["view_count"], 2)
        self.assertEqual(a["revisit_count"], 0)

    def test_same_time_views_are_all_latest(self):
        state = UserViewState()
        state.add_views(0, [C])
        state.add_views(MINUTE, [A, B])
        features = features_by_item(state, MINUTE)
        self.assertEqual(features[A]["is_last_viewed"], 1)
        self.assertEqual(features[B]["is_last_viewed"], 1)
        self.assertEqual(features[C]["is_last_viewed"], 0)

    def test_purchased_item_is_excluded_but_history_is_kept(self):
        state = UserViewState()
        state.add_views(0, [A])
        state.add_views(MINUTE, [B])
        state.mark_purchased(A)
        state.add_views(2 * MINUTE, [C])
        features = features_by_item(state, 2 * MINUTE)
        self.assertEqual(set(features), {B, C})
        # 구매한 상품도 사용자 전체 조회와 조회한 상품 수에는 남는다
        self.assertEqual(features[C]["user_total_views"], 3)
        self.assertEqual(features[C]["distinct_items_viewed"], 3)

    def test_item_purchased_before_first_view_is_not_candidate(self):
        state = UserViewState()
        state.mark_purchased(A)
        state.add_views(0, [A, B])
        self.assertEqual(set(features_by_item(state, 0)), {B})

    def test_features_are_computed_at_given_time(self):
        state = UserViewState()
        state.add_views(0, [A])
        a = features_by_item(state, 10 * MINUTE)[A]
        self.assertEqual(a["seconds_since_last_view"], 600)

    def test_capacity_grows(self):
        state = UserViewState(capacity=2)
        items = list(range(100, 150))
        for t, item in enumerate(items):
            state.add_views(t * 1000, [item])
        positions = state.candidates()
        self.assertEqual(len(positions), 50)
        np.testing.assert_array_equal(state.items[positions], items)


if __name__ == "__main__":
    unittest.main()
