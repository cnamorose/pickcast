"""guess_game.py의 문제 기준과 난이도를 손으로 만든 조회 기록으로 확인한다."""
import unittest

from guess_game import MAX_SPAN_MS, PROBLEMS_PATH, build_problem, difficulty, load_problems


def views(*items, gap_ms=60_000):
    return [(k * gap_ms, item) for k, item in enumerate(items)]


class DifficultyTest(unittest.TestCase):
    def test_easy_when_answer_alone_top_and_few_items(self):
        self.assertEqual(difficulty(["A", "B", "A"], "A"), 1)

    def test_tie_at_top_counts_as_not_alone(self):
        self.assertEqual(difficulty(["A", "B"], "A"), 2)

    def test_many_items_add_one(self):
        self.assertEqual(difficulty(["A", "A", "B", "C", "D"], "A"), 2)

    def test_hardest(self):
        self.assertEqual(difficulty(["A", "B", "B", "C", "D"], "A"), 3)


class BuildProblemTest(unittest.TestCase):
    def test_drops_last_view_of_answer(self):
        problem = build_problem(views("A", "B", "A"), "A")
        self.assertEqual([item for _, item in problem["views"]], ["A", "B"])

    def test_seconds_from_first_view(self):
        problem = build_problem(views("A", "B", "C"), "A")
        self.assertEqual([sec for sec, _ in problem["views"]], [0, 60, 120])

    def test_answer_must_remain(self):
        # 마지막 조회를 빼면 산 상품이 남지 않는다
        self.assertIsNone(build_problem(views("B", "C", "A"), "A"))

    def test_needs_two_items(self):
        self.assertIsNone(build_problem(views("A", "A", "A"), "A"))

    def test_too_many_items(self):
        self.assertIsNone(build_problem(views("A", "B", "C", "D", "E", "F", "G"), "A"))

    def test_one_shopping_only(self):
        long_gap = views("A", "B", gap_ms=MAX_SPAN_MS + 1)
        self.assertIsNone(build_problem(long_gap, "A"))


@unittest.skipUnless(PROBLEMS_PATH.exists(), "문제 파일이 없습니다")
class ProblemFileTest(unittest.TestCase):
    def test_every_level_has_problems_and_answer_was_viewed(self):
        data = load_problems()
        self.assertEqual({p["level"] for p in data["problems"]}, {1, 2, 3})
        for problem in data["problems"]:
            self.assertIn(problem["answer"], [item for _, item in problem["views"]])


if __name__ == "__main__":
    unittest.main()
