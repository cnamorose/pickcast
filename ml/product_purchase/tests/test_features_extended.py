"""features_extended.py와 item_stats.py를 손으로 만든 작은 기록으로 확인한다."""
import unittest

import numpy as np
import pandas as pd

import item_stats
from features import FEATURES, UserViewState
from features_extended import (
    ALL_FEATURES,
    EXPERIMENTS,
    SESSION_GAP_MS,
    UserEventState,
    experiment_features,
)
from split_by_time import VALID_START


MINUTE = 60_000
A, B, C = 1, 2, 3


def features_by_item(state, now):
    positions = state.candidates()
    values = state.features(now, positions)
    return {
        int(state.items[pos]): {name: values[name][k] for name in values}
        for k, pos in enumerate(positions)
    }


class UserEventStateTest(unittest.TestCase):
    def test_view_features_match_view_only_state(self):
        # 조회만 있으면 view 묶음은 기존 features.py와 같은 값이다.
        history = [(0, [A]), (1 * MINUTE, [B]), (2 * MINUTE, [A, C]), (5 * MINUTE, [A])]
        old, new = UserViewState(), UserEventState()
        for now, items in history:
            old.add_views(now, items)
            new.add_events(now, items, [])
            old_values = old.features(now, old.candidates())
            new_values = new.features(now, new.candidates())
            for name in FEATURES:
                np.testing.assert_allclose(old_values[name], new_values[name], err_msg=name)

    def test_cart_only_item_is_candidate(self):
        state = UserEventState()
        state.add_events(0, [A], [])
        state.add_events(2 * MINUTE, [], [B])
        b = features_by_item(state, 2 * MINUTE)[B]
        self.assertEqual(b["view_count"], 0)
        self.assertTrue(np.isnan(b["seconds_since_last_view"]))
        self.assertEqual(b["is_last_viewed"], 0)
        self.assertEqual(b["cart_count"], 1)
        self.assertEqual(b["seconds_since_last_cart"], 0)
        self.assertEqual(b["user_carted_items"], 1)
        self.assertEqual(b["distinct_items_viewed"], 1)
        a = features_by_item(state, 2 * MINUTE)[A]
        self.assertTrue(np.isnan(a["seconds_since_last_cart"]))
        self.assertEqual(a["is_last_viewed"], 1)

    def test_view_after_cart_is_first_view(self):
        state = UserEventState()
        state.add_events(0, [], [A])
        state.add_events(MINUTE, [A], [])
        a = features_by_item(state, MINUTE)[A]
        self.assertEqual(a["view_count"], 1)
        self.assertEqual(a["revisit_count"], 0)
        self.assertEqual(a["seconds_since_first_view"], 0)
        self.assertEqual(a["seconds_since_last_cart"], 60)

    def test_sessions(self):
        state = UserEventState()
        state.add_events(0, [A], [])
        state.add_events(MINUTE, [B], [])
        later = MINUTE + SESSION_GAP_MS + 1
        state.add_events(later, [C], [])
        c = features_by_item(state, later)[C]
        self.assertEqual(c["session_count"], 2)
        self.assertEqual(c["session_views"], 1)
        self.assertAlmostEqual(c["seconds_since_prev_session"], (later - MINUTE) / 1000, places=1)

    def test_purchase_removes_candidate_and_counts(self):
        state = UserEventState()
        state.add_events(0, [A, B], [])
        state.mark_purchased(A)
        values = features_by_item(state, MINUTE)
        self.assertEqual(set(values), {B})
        self.assertEqual(values[B]["prior_purchases"], 1)

    def test_hour_and_weekday(self):
        # 2015-08-03 14:30 UTC는 월요일
        now = int(pd.Timestamp("2015-08-03 14:30").value // 1_000_000)
        state = UserEventState()
        state.add_events(now, [A], [])
        a = features_by_item(state, now)[A]
        self.assertEqual(a["hour"], 14)
        self.assertEqual(a["weekday"], 0)

    def test_touched_now(self):
        state = UserEventState()
        state.add_events(0, [A], [])
        state.add_events(MINUTE, [], [B])
        positions = state.candidates()
        touched = dict(zip(state.items[positions].tolist(), state.touched_now(MINUTE, positions)))
        self.assertEqual(touched, {A: 0, B: 1})

    def test_experiments_use_known_features(self):
        for name in EXPERIMENTS:
            self.assertTrue(set(experiment_features(name)) <= set(ALL_FEATURES))


class ItemStatsTest(unittest.TestCase):
    def test_train_rows_exclude_own_fold(self):
        early = VALID_START - 1000
        # 사용자 5(fold 0)와 6(fold 1)이 상품 A를 봤고 5만 샀다.
        events = pd.DataFrame(
            {
                "visitorid": [5, 5, 6, 7],
                "event": ["view", "transaction", "view", "view"],
                "itemid": [A, A, A, A],
                "timestamp": [early, early, early, VALID_START],
            }
        )
        users = pd.DataFrame({"visitorid": [5, 6, 7], "split": ["train", "train", "valid"]})
        table, defaults = item_stats.compute(events, users)

        valid_row = item_stats.attach(
            pd.DataFrame({"visitorid": [7], "itemid": [A]}), "valid", table, defaults
        )
        self.assertEqual(valid_row["item_viewers"][0], 2)  # 7월 조회는 세지 않는다

        own = item_stats.attach(
            pd.DataFrame({"visitorid": [5], "itemid": [A]}), "train", table, defaults
        )
        self.assertEqual(own["item_viewers"][0], 1)  # 자기(fold 0)를 뺀 사용자 6만
        self.assertAlmostEqual(
            own["item_purchase_rate"][0],
            item_stats.PRIOR_WEIGHT * defaults["item_purchase_rate"] / (1 + item_stats.PRIOR_WEIGHT),
            places=6,
        )

        unseen = item_stats.attach(
            pd.DataFrame({"visitorid": [7], "itemid": [B]}), "valid", table, defaults
        )
        self.assertEqual(unseen["item_viewers"][0], 0)
        self.assertAlmostEqual(unseen["item_purchase_rate"][0], defaults["item_purchase_rate"], places=6)


if __name__ == "__main__":
    unittest.main()
