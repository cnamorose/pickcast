"""피크타임 우선 처리 시뮬레이션 결과 API (확장 기능 3).

시뮬레이션은 무거워 ml 쪽에서 미리 돌리고(ml/product_purchase/peak_simulation.py),
백엔드는 저장된 요약(ml/results/peak_simulation.json)만 내준다. 요청마다 파일을 읽어
결과가 바뀌어도 서버를 재시작할 필요가 없다.
"""
import json

from fastapi import APIRouter, HTTPException

from .ml import PROJECT_ROOT

router = APIRouter(tags=["peak"])

RESULTS_PATH = PROJECT_ROOT / "ml" / "results" / "peak_simulation.json"


def load_results(path=RESULTS_PATH):
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="시뮬레이션 결과가 없습니다. ml/product_purchase/peak_simulation.py를 먼저 실행하세요.",
        )
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/peak-simulation")
def get_peak_simulation():
    """선착순·확률 우선·에이징의 test 비교와 valid α 곡선."""
    return load_results()
