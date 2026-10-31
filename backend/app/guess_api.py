"""구매 맞히기 게임 API (추가 체험: 사람 vs AI).

문제는 ml 쪽에서 RetailRocket test 사용자의 조회 기록으로 미리 만든다
(ml/product_purchase/guess_game.py). 요청마다 파일을 읽어 재시작 없이 바뀐다.

- /guess-game/start: 난이도 1·2·3 문제를 하나씩 무작위로 고른다. 정답은 보내지 않는다.
- /guess-game/answer: 사람이 고른 상품을 받아 정답과 AI 예측(현재 모델)을 돌려준다.
  시간 안에 고르지 않았으면 pick 없이 보낸다(오답 처리).

난이도별 AI 정답률은 문제를 만들 때의 모델로 계산한 값이라, 모델 버전을 함께 돌려준다.
"""
import random

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .ml import FEATURE_LABELS, PROJECT_ROOT, get_predictor

from guess_game import load_problems  # noqa: E402  (ml/product_purchase)

router = APIRouter(prefix="/guess-game", tags=["guess"])

PROBLEMS_PATH = PROJECT_ROOT / "ml" / "results" / "guess_problems.json"
MISSING = "게임 문제가 없습니다. ml/product_purchase/guess_game.py를 먼저 실행하세요."
LEVELS = (1, 2, 3)
SECONDS_PER_ROUND = 30
# AI가 그 상품을 고른 이유로 보여줄 요인 수 (구매 쪽으로 기여한 피처만)
REASONS = 2
# 후보끼리 비교해 보여줄 조회 사실 (사람도 화면에서 셀 수 있는 값)
FACTS = ("view_count", "revisit_count", "seconds_since_last_view")


def load_game(path=None):
    path = path or PROBLEMS_PATH  # 테스트에서 PROBLEMS_PATH를 바꿔 끼울 수 있게 호출 때 읽는다
    if not path.exists():
        raise HTTPException(status_code=404, detail=MISSING)
    return load_problems(path)


def viewed_items(problem):
    """본 상품을 처음 본 순서대로 (중복 없이)."""
    return list(dict.fromkeys(item for _, item in problem["views"]))


def public_round(problem):
    """화면에 보낼 라운드. 정답은 빼고 보낸다."""
    return {
        "problem_id": problem["id"],
        "level": problem["level"],
        "views": [{"seconds": sec, "item_id": item} for sec, item in problem["views"]],
        "items": viewed_items(problem),
    }


def find_problem(data, problem_id):
    problems = data["problems"]
    if not 0 <= problem_id < len(problems) or problems[problem_id]["id"] != problem_id:
        raise HTTPException(status_code=404, detail="없는 문제입니다.")
    return problems[problem_id]


def ai_result(predictor, problem):
    """현재 모델의 후보별 확률 순위와, 후보마다 구매 쪽으로 가장 크게 기여한 요인."""
    views = [(sec * 1000, item) for sec, item in problem["views"]]
    prediction = predictor.predict(views)
    candidates = []
    for c in prediction["candidates"]:
        positive = sorted(
            ((name, value) for name, value in c["shap"]["contributions"].items() if value > 0),
            key=lambda pair: -pair[1],
        )[:REASONS]
        candidates.append(
            {
                "item_id": c["item_id"],
                "rank": c["rank"],
                "probability": c["probability"],
                # 상품을 한 번만 봤을 때보다 몇 배 높은지 (단계 판단과 같은 기준)
                "lift": c["probability"] / predictor.base_probability,
                "facts": {name: c["features"][name] for name in FACTS},
                "reasons": [
                    {"feature": name, "label": FEATURE_LABELS[name], "value": c["features"][name]}
                    for name, _ in positive
                ],
            }
        )
    return {"pick": candidates[0]["item_id"], "model_version": predictor.version, "candidates": candidates}


@router.get("/start")
def start_game(seed: int | None = Query(None, description="같은 문제를 다시 받고 싶을 때 (테스트용)")):
    """난이도 1·2·3 문제 하나씩과 라운드 시간, 난이도별 AI 정답률."""
    data = load_game()
    rng = random.Random(seed)
    rounds = []
    for level in LEVELS:
        pool = [p for p in data["problems"] if p["level"] == level]
        if not pool:
            raise HTTPException(status_code=404, detail=f"난이도 {level} 문제가 없습니다.")
        rounds.append(public_round(rng.choice(pool)))
    return {
        "rounds": rounds,
        "seconds_per_round": SECONDS_PER_ROUND,
        "ai_accuracy": data["ai_accuracy"],
        "settings": data["settings"],
    }


class AnswerIn(BaseModel):
    problem_id: int
    # 시간 안에 고르지 않았으면 비워서 보낸다
    pick: int | None = None


@router.post("/answer")
def answer(body: AnswerIn):
    """정답, 사람의 결과, AI의 선택과 후보별 확률."""
    problem = find_problem(load_game(), body.problem_id)
    if body.pick is not None and body.pick not in viewed_items(problem):
        raise HTTPException(status_code=400, detail="이 기록에서 본 상품 중에서 골라야 합니다.")
    ai = ai_result(get_predictor(), problem)
    return {
        "problem_id": problem["id"],
        "level": problem["level"],
        "answer": problem["answer"],
        "pick": body.pick,
        "timed_out": body.pick is None,
        "correct": body.pick == problem["answer"],
        "ai": {**ai, "correct": ai["pick"] == problem["answer"]},
    }
