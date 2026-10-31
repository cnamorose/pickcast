"""guess_api.py가 정답을 숨긴 라운드를 주고, 답을 받으면 정답과 AI 예측을 돌려주는지 확인한다."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.app import guess_api
from backend.app.guess_api import AnswerIn, answer, load_game, start_game

# 손으로 만든 문제 3개 (난이도 1·2·3). 상품 10을 여러 번 본 사용자가 10을 샀다.
PROBLEMS = {
    "settings": {"model_version": "test"},
    "ai_accuracy": {"1": {"problems": 1, "ai_hits": 1, "ai_rate": 1.0}},
    "problems": [
        {"id": 0, "level": 1, "answer": 10, "views": [[0, 10], [30, 20], [60, 10], [90, 10]]},
        {"id": 1, "level": 2, "answer": 20, "views": [[0, 10], [40, 20]]},
        {"id": 2, "level": 3, "answer": 30, "views": [[0, 10], [10, 20], [20, 30], [30, 40]]},
    ],
}


class GuessApiTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "guess.json"
        self.path.write_text(json.dumps(PROBLEMS), encoding="utf-8")
        self.original = guess_api.PROBLEMS_PATH
        guess_api.PROBLEMS_PATH = self.path

    def tearDown(self):
        guess_api.PROBLEMS_PATH = self.original
        shutil.rmtree(self.dir)

    def test_missing_file(self):
        with self.assertRaises(HTTPException) as caught:
            load_game(self.dir / "none.json")
        self.assertEqual(caught.exception.status_code, 404)

    def test_start_gives_one_round_per_level_without_answer(self):
        game = start_game(seed=1)
        self.assertEqual([r["level"] for r in game["rounds"]], [1, 2, 3])
        self.assertEqual(game["seconds_per_round"], 30)
        for r in game["rounds"]:
            self.assertNotIn("answer", r)
        # 본 상품은 처음 본 순서대로 중복 없이
        self.assertEqual(game["rounds"][0]["items"], [10, 20])

    def test_correct_answer_and_ai_ranking(self):
        result = answer(AnswerIn(problem_id=0, pick=10))
        self.assertTrue(result["correct"])
        self.assertFalse(result["timed_out"])
        ai = result["ai"]
        self.assertEqual(ai["pick"], ai["candidates"][0]["item_id"])
        self.assertEqual(ai["correct"], ai["pick"] == 10)
        self.assertEqual(sorted(c["item_id"] for c in ai["candidates"]), [10, 20])
        self.assertEqual([c["rank"] for c in ai["candidates"]], [1, 2])
        # 상품 10은 세 번 봤다 (마지막 조회 기준 사실)
        facts = {c["item_id"]: c["facts"] for c in ai["candidates"]}
        self.assertEqual(facts[10]["view_count"], 3)

    def test_timeout_is_wrong(self):
        result = answer(AnswerIn(problem_id=1))
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["correct"])

    def test_pick_must_be_viewed_item(self):
        with self.assertRaises(HTTPException) as caught:
            answer(AnswerIn(problem_id=1, pick=99))
        self.assertEqual(caught.exception.status_code, 400)

    def test_unknown_problem(self):
        with self.assertRaises(HTTPException) as caught:
            answer(AnswerIn(problem_id=7, pick=10))
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
