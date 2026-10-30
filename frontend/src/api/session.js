// 백엔드 세션 API 호출.
// 체험 한 번 = 세션 하나. 조회·결제를 할 때마다 서버 DB에 저장한다.
// 요청/응답 형식은 backend/README.md 의 API 표를 따름.

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options = {}) {
  // 본문이 있는 요청에만 Content-Type을 붙인다.
  // GET에도 붙이면 브라우저가 CORS 사전 확인(OPTIONS)을 한 번 더 보낸다.
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
  });

  if (!res.ok) {
    throw new Error(`서버 응답 오류 (status ${res.status})`);
  }

  return res.json();
}

// 새 세션을 만든다. 이전 세션이 결제 없이 끝났으면 서버가 abandoned로 닫는다.
export function createSession(previousSessionId) {
  return request("/sessions", {
    method: "POST",
    body: JSON.stringify({ previous_session_id: previousSessionId || null }),
  }); // { session_id }
}

// 조회 한 건 저장. 조회 시각은 서버가 기록한다.
export function sendView(sessionId, itemId) {
  return request(`/sessions/${sessionId}/views`, {
    method: "POST",
    body: JSON.stringify({ item_id: itemId }),
  }); // { prediction: {...}, stage }
}

// 결제 저장. 세션이 purchased로 닫힌다.
export function sendPurchase(sessionId, itemId) {
  return request(`/sessions/${sessionId}/purchases`, {
    method: "POST",
    body: JSON.stringify({ item_id: itemId }),
  });
}

// 결과 화면용 예측. 서버가 이 세션의 조회 기록으로 계산한다.
export function fetchSessionPrediction(sessionId) {
  return request(`/sessions/${sessionId}/predictions`);
  // { prediction: {...}, timeline: [...], feature_labels: {...} }
}

// 판매자 대시보드. 지금 쇼핑 중인 세션의 상품별 예상 구매, 단계별 인원, 자주 비교되는 상품 쌍
export function fetchDashboard() {
  return request("/dashboard");
  // { generated_at, active_sessions, active_window_minutes, products: [...], stages, compare_pairs, insights }
}
