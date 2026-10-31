import { Link } from "react-router-dom";
import { productLabel } from "./products";
import { maxPoints, points } from "./score";

const CONFETTI = ["🎉", "✨", "🛒", "⭐", "🎊"];

function verdictText(me, ai) {
  if (me > ai) return "AI를 이겼어요! 🎉";
  if (me < ai) return "이번엔 AI가 이겼어요. 한 번 더?";
  return "무승부! 막상막하네요";
}

// 3라운드가 끝난 뒤의 대시보드: 점수, 라운드별 결과, 난이도별 AI 전체 정답률
export default function FinalBoard({ game, results, productOf, onRestart }) {
  const me = points(results, "me");
  const ai = points(results, "ai");
  const total = maxPoints(game.rounds);
  const levels = Object.entries(game.ai_accuracy);

  return (
    <section className="guess-final">
      <div className="guess-panel guess-score">
        {me > ai && (
          <div className="guess-confetti" aria-hidden="true">
            {Array.from({ length: 24 }, (_, i) => (
              <span key={i} style={{ left: `${(i * 37) % 100}%`, animationDelay: `${(i % 8) * 0.12}s` }}>
                {CONFETTI[i % CONFETTI.length]}
              </span>
            ))}
          </div>
        )}
        <span className="guess-round-no">최종 결과 ({total}점 만점)</span>
        <div className="guess-score-row">
          <div>
            <span>🙂 나</span>
            <b>{me}</b>
          </div>
          <i>:</i>
          <div>
            <span>🤖 AI</span>
            <b>{ai}</b>
          </div>
        </div>
        <p>{verdictText(me, ai)}</p>
      </div>

      <div className="guess-final-rounds">
        {results.map((r, i) => {
          const answer = productOf[r.answer];
          return (
            <div key={r.problem_id} className="guess-panel guess-final-card">
              <span className="guess-round-no">
                라운드 {i + 1} · 난이도 {"★".repeat(r.level)} · {r.level}점
              </span>
              <img src={answer.image} alt="" />
              <b>{productLabel(answer)}</b>
              <ul>
                <li className={r.correct ? "is-hit" : "is-miss"}>
                  🙂 {r.correct ? `✓ +${r.level}점` : "✕"} {r.timed_out ? "시간 초과" : productLabel(productOf[r.pick])}
                </li>
                <li className={r.ai.correct ? "is-hit" : "is-miss"}>
                  🤖 {r.ai.correct ? `✓ +${r.level}점` : "✕"} {productLabel(productOf[r.ai.pick])}
                </li>
              </ul>
            </div>
          );
        })}
      </div>

      <div className="guess-panel">
        <h3>난이도별 AI 정답률 (전체 문제)</h3>
        <p className="guess-hint">
          모델이 학습에서 보지 않은 test 사용자 기록으로 만든 문제 전체에서, AI가 1순위로 맞힌 비율이에요 (
          {game.settings.model_version} 기준).
        </p>
        <div className="guess-accuracy">
          {levels.map(([level, a]) => (
            <div key={level}>
              <span>난이도 {"★".repeat(Number(level))}</span>
              <div className="guess-accuracy-bar">
                <i style={{ width: `${a.ai_rate * 100}%` }} />
              </div>
              <b>{Math.round(a.ai_rate * 100)}%</b>
              <small>{a.problems}문제</small>
            </div>
          ))}
        </div>
      </div>

      <div className="guess-actions">
        <button className="btn btn-black" onClick={onRestart}>
          다시 하기
        </button>
        <Link to="/" className="btn guess-btn-outline">
          처음으로
        </Link>
      </div>
    </section>
  );
}
