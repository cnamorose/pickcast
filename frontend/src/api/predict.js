// 백엔드 /predictions 엔드포인트 호출.
// 요청/응답 형식은 docs/ml/product-purchase-inference-guide.md 의 FastAPI 예시를 따름.

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function fetchPrediction(views) {
  const res = await fetch(`${API_BASE}/predictions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      views: views.map((v) => ({ timestamp: v.timestamp, item_id: v.item_id })),
    }),
  });

  if (!res.ok) {
    throw new Error(`예측 서버 응답 오류 (status ${res.status})`);
  }

  return res.json(); // { prediction: {...}, timeline: [...], feature_labels: {...} }
}
