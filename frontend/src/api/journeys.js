// 시뮬레이션(같은 시간대 손님들 + 가게 전체 대시보드) API 호출.
// 응답 형식은 backend/README.md 의 "시뮬레이션" 항목을 따름.

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function get(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`서버 응답 오류 (status ${res.status})`);
  }
  return res.json();
}

// 시간 창과 화면 탭에 띄울 손님 목록·결과 요약
export function fetchJourneys() {
  return get("/journeys");
}

// 가게 전체 대시보드 (1분마다 예상 판매, 곧 팔릴 상품, 가정 재고·알림, 팔린 상품)
export function fetchStore() {
  return get("/journeys/store");
}

// 손님 한 명의 행동별 기록과 그 순간 그 손님의 예측
export function fetchJourney(id) {
  return get(`/journeys/${id}`);
}
