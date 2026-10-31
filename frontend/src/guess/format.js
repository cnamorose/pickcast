// 초를 "1분 35초", "2시간 10분"처럼 읽기 쉽게 바꾼다.
export function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}초`;
  if (s < 3600) {
    const rest = s % 60;
    return rest ? `${Math.floor(s / 60)}분 ${rest}초` : `${Math.floor(s / 60)}분`;
  }
  const minutes = Math.floor((s % 3600) / 60);
  return minutes ? `${Math.floor(s / 3600)}시간 ${minutes}분` : `${Math.floor(s / 3600)}시간`;
}

// 조회 타임라인 한 줄마다: 앞 조회와의 간격, 이미 본 상품을 다시 본 것인지
export function timelineRows(views) {
  const seen = new Set();
  return views.map((view, i) => {
    const row = {
      ...view,
      gap: i === 0 ? null : view.seconds - views[i - 1].seconds,
      again: seen.has(view.item_id),
    };
    seen.add(view.item_id);
    return row;
  });
}
