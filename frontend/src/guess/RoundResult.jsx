import { formatDuration } from "./format";
import { productLabel } from "./products";

// AI가 고른 상품의 조회 사실로 한마디를 만든다 (모델이 실제로 보는 값만 쓴다)
function aiComment(candidate, label) {
  const { view_count: views, revisit_count: revisits, seconds_since_last_view: since } = candidate.facts;
  const reasons = [];
  if (views >= 2) reasons.push(`${views}번이나 봤고`);
  if (revisits >= 1) reasons.push(`다른 상품을 보다가 ${revisits}번 다시 돌아왔어요`);
  else if (since < 60) reasons.push("가장 최근까지 보고 있었어요");
  if (reasons.length === 0) reasons.push("다른 후보보다 구매 확률이 가장 높게 나왔어요");
  return `${label}을(를) ${reasons.join(" ")}. 저는 이 상품!`;
}

// 나와 AI의 선택을 동시에 뒤집어 공개하는 카드
function RevealCard({ who, icon, product, correct, points, note, delay }) {
  return (
    <div className={`guess-reveal ${correct ? "is-hit" : "is-miss"}`} style={{ animationDelay: `${delay}s` }}>
      <span className="guess-reveal-who">
        {icon} {who}
      </span>
      {product ? <img src={product.image} alt="" /> : <div className="guess-reveal-empty">⏰</div>}
      <span className="guess-reveal-name">{product ? productLabel(product) : note}</span>
      <b>{correct ? `✓ 정답 +${points}점` : "✕ 오답"}</b>
    </div>
  );
}

// 라운드 결과: 동시 공개, 정답, AI 한마디, AI가 본 후보별 순위와 그 근거가 된 조회 사실
export default function RoundResult({ index, result, productOf, isLast, onNext }) {
  const answer = productOf[result.answer];
  const aiTop = result.ai.candidates[0];
  const maxLift = Math.max(...result.ai.candidates.map((c) => c.lift));

  return (
    <section className="guess-result">
      <div className="guess-panel guess-answer">
        <span className="guess-round-no">
          라운드 {index + 1} · 난이도 {"★".repeat(result.level)} 공개!
        </span>
        <div className="guess-reveals">
          <RevealCard
            who="나"
            icon="🙂"
            product={result.timed_out ? null : productOf[result.pick]}
            correct={result.correct}
            points={result.level}
            note="시간 초과"
            delay={0}
          />
          <RevealCard
            who="AI"
            icon="🤖"
            product={productOf[result.ai.pick]}
            correct={result.ai.correct}
            points={result.level}
            delay={0.15}
          />
        </div>
        <div className="guess-answer-line">
          <img src={answer.image} alt="" />
          <span>
            실제로 산 상품은 <b>{productLabel(answer)}</b>
          </span>
        </div>
        <p className="guess-ai-comment">🤖 {aiComment(aiTop, productLabel(productOf[aiTop.item_id]))}</p>
      </div>

      <div className="guess-panel">
        <h3>AI가 본 구매 가능성</h3>
        <p className="guess-hint">평소(상품을 한 번만 봤을 때)보다 구매 확률이 몇 배인지예요. 숫자는 기록 끝 시점 기준이에요.</p>
        <ol className="guess-ranking">
          {result.ai.candidates.map((c) => {
            const product = productOf[c.item_id];
            const isAnswer = c.item_id === result.answer;
            return (
              <li key={c.item_id} className={isAnswer ? "is-answer" : ""}>
                <span className="guess-rank">{c.rank}</span>
                <img src={product.image} alt="" />
                <div className="guess-rank-body">
                  <div className="guess-rank-title">
                    {productLabel(product)}
                    {isAnswer && <em>정답</em>}
                  </div>
                  <div className="guess-lift">
                    <i style={{ width: `${(c.lift / maxLift) * 100}%` }} />
                  </div>
                  <small>
                    조회 {c.facts.view_count}회 · 다른 상품을 보고 돌아온 횟수 {c.facts.revisit_count}회 · 마지막 조회 후{" "}
                    {formatDuration(c.facts.seconds_since_last_view)}
                  </small>
                </div>
                <b className="guess-lift-value">{c.lift.toFixed(1)}배</b>
              </li>
            );
          })}
        </ol>
        <button className="btn btn-black" onClick={onNext}>
          {isLast ? "최종 결과 보기 →" : "다음 라운드 →"}
        </button>
      </div>
    </section>
  );
}
