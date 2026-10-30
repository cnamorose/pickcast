// 피크타임 우선 처리 시뮬레이션 API 호출.
// 응답 형식은 backend/README.md 의 "피크타임" 항목을 따름.

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function get(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`서버 응답 오류 (status ${res.status})`);
  }
  return res.json();
}

// 100개 시간대 전체 결과: 세 방식 비교, α 곡선
export function fetchPeakResults() {
  return get("/peak-simulation");
}

// 재생할 수 있는 시간대 목록
export function fetchPeakWindows() {
  return get("/peak-simulation/windows");
}

// 시간대 하나를 한 방식으로 재생한 사건 기록
export function fetchPeakReplay({ window, policy, alpha, overload }) {
  const params = new URLSearchParams({ window, policy, alpha, overload });
  return get(`/peak-simulation/replay?${params}`);
}
