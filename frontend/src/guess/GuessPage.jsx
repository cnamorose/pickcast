import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { startGuessGame, submitGuess } from "../api/guess";
import FinalBoard from "./FinalBoard";
import { assignProducts } from "./products";
import RoundResult from "./RoundResult";
import RoundView from "./RoundView";
import { maxPoints, points } from "./score";
import "./guess.css";

// 위쪽 점수판: 나 vs AI 점수와 라운드별 결과 점
function VsBar({ game, results, index, phase }) {
  const dots = (who) =>
    game.rounds.map((round, i) => {
      const r = results[i];
      const correct = r && (who === "ai" ? r.ai.correct : r.correct);
      const state = !r ? (i === index && phase === "round" ? "is-now" : "") : correct ? "is-hit" : "is-miss";
      return (
        <span key={i} className={`guess-dot ${state}`} title={`라운드 ${i + 1} (${round.level}점)`}>
          {r ? (correct ? "✓" : "✕") : round.level}
        </span>
      );
    });
  return (
    <div className="guess-vs">
      <div className="guess-vs-side">
        <span className="guess-vs-name">🙂 나</span>
        <b>{points(results, "me")}</b>
        <div className="guess-dots">{dots("me")}</div>
      </div>
      <span className="guess-vs-mark">VS</span>
      <div className="guess-vs-side is-ai">
        <span className="guess-vs-name">🤖 AI</span>
        <b>{points(results, "ai")}</b>
        <div className="guess-dots">{dots("ai")}</div>
      </div>
      <small className="guess-vs-max">{maxPoints(game.rounds)}점 만점</small>
    </div>
  );
}

const TITLE = "AI와 대결";
// 제목에서 강조색으로 칠할 앞 글자 수 ("AI")
const TITLE_ACCENT = 2;

// 게임 규칙. 첫 화면의 "게임 설명" 창에서 보여준다. [아이콘, 굵은 제목, 설명]
const RULES = [
  ["🛒", "실제 쇼핑 기록", "실제 쇼핑몰(RetailRocket) 고객이 어떤 상품을 몇 번, 어떤 간격으로 봤는지 보여드려요."],
  ["⏱", "재생을 보고 30초 안에", "손님이 상품 사이를 오가는 모습을 먼저 보고, 30초 안에 산 상품을 골라요. 시간이 지나면 오답이에요."],
  ["⭐", "난이도만큼 점수", "3라운드, 난이도 ★ → ★★ → ★★★. 맞히면 1·2·3점을 받아요 (6점 만점)."],
  ["🤖", "공정한 대결", "AI도 같은 기록만 보고 맞혀요. AI가 학습할 때 본 적 없는 사람들의 기록이에요."],
  ["🔒", "중간에 나갈 수 없어요", "게임을 시작하면 3라운드가 끝날 때까지 이어져요."],
];

function RulesModal({ onClose }) {
  return (
    <div className="guess-modal-overlay" onClick={onClose}>
      <div className="guess-panel guess-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h2>게임 설명</h2>
        <ul className="guess-rules">
          {RULES.map(([icon, title, desc]) => (
            <li key={title}>
              <span className="guess-rule-icon" aria-hidden="true">
                {icon}
              </span>
              <div>
                <b>{title}</b>
                <p>{desc}</p>
              </div>
            </li>
          ))}
        </ul>
        <button className="btn btn-black" onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}

// 구매 맞히기 게임 (추가 체험: 사람 vs AI).
// 쇼핑 체험과 별개라 세션을 만들지 않는다.
// 첫 화면(시작·설명·종료) → (라운드 → 라운드 결과) × 3 → 최종 대시보드.
// 게임 중에는 나가는 버튼을 두지 않는다. "게임 종료"는 첫 화면과 최종 화면에만 있다.
export default function GuessPage() {
  const [phase, setPhase] = useState("intro"); // intro | loading | round | result | final
  const [game, setGame] = useState(null);
  const [productOf, setProductOf] = useState({});
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);
  const [showRules, setShowRules] = useState(false);
  const navigate = useNavigate();
  const intro = phase === "intro" || phase === "loading";

  async function start() {
    setPhase("loading");
    setError(null);
    try {
      const next = await startGuessGame();
      setGame(next);
      setProductOf(assignProducts(next.rounds));
      setIndex(0);
      setResults([]);
      setPhase("round");
    } catch (err) {
      setError(err.message);
      setPhase("intro");
    }
  }

  async function answer(pick) {
    try {
      const result = await submitGuess(game.rounds[index].problem_id, pick);
      setResults((prev) => [...prev, result]);
      setPhase("result");
    } catch (err) {
      setError(err.message);
      setPhase("intro");
    }
  }

  function next() {
    if (index + 1 < game.rounds.length) {
      setIndex(index + 1);
      setPhase("round");
    } else {
      setPhase("final");
    }
  }

  return (
    <div className={`guess-page ${intro ? "guess-page-intro" : ""}`}>
      {game && !intro && (
        <VsBar game={game} results={results} index={index} phase={phase} />
      )}

      {intro && (
        <section className="guess-intro">
          {/* 글자마다 차례로 통통 튀는 제목 */}
          <h1 className="guess-title" aria-label={TITLE}>
            {[...TITLE].map((ch, i) => (
              <span
                key={i}
                aria-hidden="true"
                className={i < TITLE_ACCENT ? "is-accent" : ""}
                style={{ animationDelay: `${i * 0.12}s` }}
              >
                {ch === " " ? "\u00a0" : ch}
              </span>
            ))}
          </h1>
          <div className="guess-versus" aria-label="나 대 AI">
            <span>🙂 나</span>
            <b>VS</b>
            <span>🤖 AI</span>
          </div>
          <p className="guess-subtitle">실제 쇼핑 기록을 보고, 이 사람이 산 상품을 맞혀 보세요</p>
          {error && <p className="guess-error">{error} — 백엔드 서버가 켜져 있는지 확인해주세요.</p>}
          <div className="guess-menu">
            <button className="btn btn-black" onClick={start} disabled={phase === "loading"}>
              {phase === "loading" ? "문제 불러오는 중..." : "게임 시작"}
            </button>
            <button className="btn guess-btn-outline" onClick={() => setShowRules(true)}>
              게임 설명
            </button>
            <button className="btn guess-btn-outline" onClick={() => navigate("/")}>
              게임 종료
            </button>
          </div>
        </section>
      )}

      {showRules && <RulesModal onClose={() => setShowRules(false)} />}

      {phase === "round" && (
        <RoundView
          key={game.rounds[index].problem_id}
          round={game.rounds[index]}
          index={index}
          total={game.rounds.length}
          seconds={game.seconds_per_round}
          productOf={productOf}
          onSubmit={answer}
        />
      )}

      {phase === "result" && (
        <RoundResult
          index={index}
          result={results[index]}
          productOf={productOf}
          isLast={index + 1 === game.rounds.length}
          onNext={next}
        />
      )}

      {phase === "final" && <FinalBoard game={game} results={results} productOf={productOf} onRestart={start} />}

      <p className="guess-attribution">
        상품 이미지와 이름은 이해를 돕기 위해 임의로 붙인 것으로, 실제 상품과 관계없어요. · 데이터: Retailrocket recommender
        system dataset (CC BY-NC-SA 4.0)
      </p>
    </div>
  );
}
