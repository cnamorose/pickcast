import { useState } from "react";
import { Link } from "react-router-dom";
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

// 구매 맞히기 게임 (추가 체험: 사람 vs AI).
// 쇼핑 체험과 별개라 세션을 만들지 않는다.
// 안내 → (라운드 → 라운드 결과) × 3 → 최종 대시보드
export default function GuessPage() {
  const [phase, setPhase] = useState("intro"); // intro | loading | round | result | final
  const [game, setGame] = useState(null);
  const [productOf, setProductOf] = useState({});
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState([]);
  const [error, setError] = useState(null);

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
    <div className="guess-page">
      <header className="guess-topbar">
        <Link to="/" className="guess-back">
          ← 처음으로
        </Link>
        <h1>AI와 대결: 무엇을 샀을까?</h1>
      </header>

      {game && phase !== "intro" && phase !== "loading" && (
        <VsBar game={game} results={results} index={index} phase={phase} />
      )}

      {(phase === "intro" || phase === "loading") && (
        <section className="guess-panel guess-intro">
          <h2>실제 쇼핑 기록을 보고, 이 사람이 산 상품을 맞혀 보세요</h2>
          <ul>
            <li>실제 쇼핑몰(RetailRocket)의 조회 기록이에요. 어떤 상품을 몇 번, 어떤 간격으로 봤는지 보여드려요.</li>
            <li>손님이 상품 사이를 오가는 모습을 먼저 보여드린 뒤, 30초 안에 산 상품을 골라요.</li>
            <li>3라운드, 난이도 ★ → ★★ → ★★★. 맞히면 난이도만큼 점수(1·2·3점, 6점 만점)를 받아요.</li>
            <li>AI도 같은 기록만 보고 맞혀요. AI가 학습할 때 본 적 없는 사람들의 기록이에요.</li>
          </ul>
          {error && <p className="guess-error">{error} — 백엔드 서버가 켜져 있는지 확인해주세요.</p>}
          <button className="btn btn-black" onClick={start} disabled={phase === "loading"}>
            {phase === "loading" ? "문제 불러오는 중..." : "게임 시작"}
          </button>
        </section>
      )}

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
