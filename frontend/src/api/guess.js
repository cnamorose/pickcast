// 구매 맞히기 게임(사람 vs AI) API 호출.
// 응답 형식은 backend/README.md 의 "구매 맞히기 게임" 항목을 따름.

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`서버 응답 오류 (status ${res.status})`);
  }
  return res.json();
}

// 난이도 1·2·3 문제 하나씩 (정답 없음), 라운드 시간, 난이도별 AI 정답률
export function startGuessGame() {
  return request("/guess-game/start");
}

// 고른 상품 제출. 시간 초과면 pick을 null로 보낸다.
export function submitGuess(problemId, pick) {
  return request("/guess-game/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(pick == null ? { problem_id: problemId } : { problem_id: problemId, pick }),
  });
}
