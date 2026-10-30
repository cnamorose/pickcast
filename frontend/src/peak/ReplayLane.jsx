import { LOW_SCORE, stateAt } from "./playback";

// 점수(구매 확률이 기준의 몇 배인지)에 따라 색을 나눈다. 1.5배 미만은 구경 수준.
export function scoreLevel(score) {
  if (score >= 3) return "high";
  if (score >= LOW_SCORE) return "mid";
  return "low";
}

// 이 방식에서 다음에 처리될 순서대로 대기열을 정렬한다 (서버의 처리 순서와 같은 기준).
function queueOrder(waiting, policy, alpha) {
  const key =
    policy === "fifo"
      ? (e) => e.t
      : (e) => -(e.score - (policy === "aging" ? alpha : 0) * e.t);
  return [...waiting].sort((a, b) => key(a) - key(b));
}

const MAX_CHIPS = 80;
// 구매 고객이 떠난 뒤 알림을 보여주는 시간 (재생 시간 기준 초)
const ALERT_SECONDS = 4;

// 한 처리 방식의 재생 화면: 지표, 대기열, 최근 처리·이탈
export default function ReplayLane({ title, subtitle, replay, time, variant }) {
  const state = stateAt(replay, time);
  if (!state) return <section className="peak-lane peak-lane-empty">불러오는 중...</section>;

  const queue = queueOrder(state.waiting, replay.policy, replay.alpha);
  // 알림 시간 안에 떠난 구매 고객을 모두 모은다 (연달아 떠나도 한 줄에 다 보이게)
  const lost = state.buyerLeaves.filter((e) => time - e.t < ALERT_SECONDS);
  const latest = lost.at(-1);
  return (
    <section className={`peak-lane peak-lane-${variant} ${latest ? "peak-lane-alert" : ""}`}>
      {/* key를 가장 최근 사건으로 바꿔서 새로 떠날 때마다 깜빡임이 다시 시작되게 한다 */}
      {latest && <div key={latest.request} className="peak-lane-flash" />}
      <header>
        <h3>{title}</h3>
        <span>{subtitle}</span>
      </header>

      <div className="peak-alert-slot">
        {latest && (
          <div key={latest.request} className="peak-alert">
            🛒 구매 고객 손님 {lost.map((e) => e.user).join(", ")}이 기다리다 떠났어요
            {lost.length > 1 ? ` (${lost.length}명)` : ""}
          </div>
        )}
      </div>

      <div className="peak-stats">
        <div className="peak-stat-buyers">
          <b>
            {state.protectedBuyers}/{state.buyers}
          </b>
          <span>지킨 구매 고객</span>
        </div>
        <div>
          <b>{state.served}</b>
          <span>처리</span>
        </div>
        <div className="peak-stat-left">
          <b>{state.left}</b>
          <span>떠난 고객</span>
        </div>
        <div>
          <b>{queue.length}</b>
          <span>대기 중</span>
        </div>
      </div>

      <div className="peak-queue" aria-label="대기열 (왼쪽부터 다음 처리 순서)">
        {queue.slice(0, MAX_CHIPS).map((e) => (
          <span key={e.request} className={`peak-chip peak-chip-${scoreLevel(e.score)}`} title={`손님 ${e.user} · ${e.score}배`}>
            {e.buyer ? "🛒" : ""}
            {e.score.toFixed(1)}
          </span>
        ))}
        {queue.length > MAX_CHIPS && <span className="peak-more">+{queue.length - MAX_CHIPS}</span>}
        {queue.length === 0 && <span className="peak-empty">대기 없음</span>}
      </div>

      <ul className="peak-recent">
        {state.recent.map((e, i) => (
          <li
            key={`${e.event}-${e.request}-${i}`}
            className={`peak-recent-item ${
              e.event === "served" ? "peak-recent-served" : e.buyer ? "peak-recent-buyer" : "peak-recent-left"
            }`}
          >
            <span>
              {e.event === "served" ? "✓ 처리" : e.buyer ? "🛒 떠남" : "✕ 떠남"} · 손님 {e.user}
            </span>
            <b>{e.event === "served" ? `${e.wait.toFixed(1)}초 대기` : e.buyer ? "구매 고객 놓침" : "기다리다 떠남"}</b>
          </li>
        ))}
      </ul>
    </section>
  );
}
