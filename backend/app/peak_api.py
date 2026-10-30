"""피크타임 우선 처리 시뮬레이션 결과·재생 API (확장 기능 3).

- /peak-simulation: 100개 시간대 전체 결과 요약. 시뮬레이션은 무거워 ml 쪽에서 미리 돌린다
  (ml/product_purchase/peak_simulation.py). 요청마다 파일을 읽어 재시작 없이 바뀐다.
- /peak-simulation/windows, /peak-simulation/replay: 재생 화면용. 저장된 시간대 하나를
  요청받은 방식으로 바로 재생해 도착·처리·이탈 사건을 돌려준다. 시간대 하나는 요청 300개
  안팎이라 가볍다. 시간대 하나의 결과는 흔들리므로 효과는 전체 결과로 말한다.
"""
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from .ml import PROJECT_ROOT

from peak_simulation import load_replay_windows, replay  # noqa: E402  (ml/product_purchase)

router = APIRouter(prefix="/peak-simulation", tags=["peak"])

RESULTS_PATH = PROJECT_ROOT / "ml" / "results" / "peak_simulation.json"
REPLAY_WINDOWS_PATH = PROJECT_ROOT / "ml" / "results" / "peak_replay_windows.json"
MISSING = "시뮬레이션 결과가 없습니다. ml/product_purchase/peak_simulation.py를 먼저 실행하세요."


def load_results(path=RESULTS_PATH):
    if not path.exists():
        raise HTTPException(status_code=404, detail=MISSING)
    return json.loads(path.read_text(encoding="utf-8"))


def load_windows(path=REPLAY_WINDOWS_PATH):
    if not path.exists():
        raise HTTPException(status_code=404, detail=MISSING)
    return load_replay_windows(path)


@router.get("")
def get_peak_simulation():
    """선착순·확률 우선·에이징의 test 비교와 valid·test α 곡선."""
    return load_results()


@router.get("/windows")
def get_windows():
    """재생할 수 있는 시간대 목록."""
    return {
        "windows": [
            {
                "window": index,
                "hour_utc": window["hour_utc"],
                "buyers": window["buyers"],
                "requests": len(window["requests"]),
                "users": len({r.user for r in window["requests"]}),
            }
            for index, window in enumerate(load_windows())
        ],
        "note": "시간대 하나의 예시입니다. 효과는 /peak-simulation의 전체 결과 기준으로 판단하세요.",
    }


@router.get("/replay")
def get_replay(
    window: int = Query(0, ge=0, description="시간대 번호 (/peak-simulation/windows)"),
    policy: Literal["fifo", "priority", "aging"] = Query("aging", description="처리 방식"),
    alpha: float = Query(20.0, ge=0, le=1000, description="에이징 계수 (aging일 때만)"),
    overload: float = Query(1.5, ge=1.0, le=5.0, description="과부하 배수 (서버 처리량 = 도착 ÷ 과부하)"),
):
    """시간대 하나를 한 방식으로 재생한 사건 기록과 요약."""
    windows = load_windows()
    if window >= len(windows):
        raise HTTPException(status_code=404, detail=f"시간대는 0~{len(windows) - 1}번까지 있습니다.")
    alpha = alpha if policy == "aging" else 0.0
    result = replay(windows[window]["requests"], policy, alpha, overload)
    return {
        "window": window,
        "hour_utc": windows[window]["hour_utc"],
        "overload": overload,
        **result,
    }
