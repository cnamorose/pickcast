import { useEffect, useMemo, useRef, useState } from "react";
import { formatDuration, timelineRows } from "./format";
import { productLabel } from "./products";

// 라운드 하나: 라운드 소개와 3·2·1 → 손님이 상품 사이를 오가는 재생 → 30초 안에 산 상품 고르기.
// 타이머는 재생이 끝난 뒤부터 센다. 시간이 다 되면 고르지 않은 채로 제출한다.
// 부모가 라운드마다 key를 바꿔 주므로, 상태는 라운드마다 새로 시작한다.
const COUNTDOWN = 3;
const URGENT_SECONDS = 5;

// 조회 하나를 보여주는 시간. 재생 전체가 8초 안팎이 되게 하되 너무 빠르거나 느리지 않게.
function stepDelay(views) {
  return Math.min(1000, Math.max(500, 8000 / views));
}

// 지금 장면을 한 줄로 말해 주는 말풍선
function bubbleText(row, product) {
  if (!row) return "";
  const label = productLabel(product);
  if (row.gap == null) return `처음 본 상품: ${label}`;
  return row.again ? `${formatDuration(row.gap)} 뒤, 다시 ${label}로!` : `${formatDuration(row.gap)} 뒤 → ${label}`;
}

export default function RoundView({ round, index, total, seconds, productOf, onSubmit }) {
  const [stage, setStage] = useState("countdown"); // countdown | replay | choose
  const [count, setCount] = useState(COUNTDOWN);
  const [step, setStep] = useState(-1); // 지금까지 재생한 조회의 번호
  const [replaying, setReplaying] = useState(false);
  const [selected, setSelected] = useState(null);
  const [remaining, setRemaining] = useState(seconds);
  const [submitting, setSubmitting] = useState(false);
  const submitted = useRef(false);
  const rows = useMemo(() => timelineRows(round.views), [round]);
  const delay = stepDelay(rows.length);

  function submit(pick) {
    if (submitted.current) return;
    submitted.current = true;
    setSubmitting(true);
    onSubmit(pick);
  }

  // 3·2·1
  useEffect(() => {
    if (stage !== "countdown") return undefined;
    if (count === 0) {
      setStage("replay");
      setStep(0);
      setReplaying(true);
      return undefined;
    }
    const t = setTimeout(() => setCount((c) => c - 1), 700);
    return () => clearTimeout(t);
  }, [stage, count]);

  // 재생: 조회를 하나씩 보여주고, 처음 재생이 끝나면 고르기 단계로
  useEffect(() => {
    if (!replaying) return undefined;
    const last = step >= rows.length - 1;
    const t = setTimeout(() => {
      if (last) {
        setReplaying(false);
        setStage((s) => (s === "replay" ? "choose" : s));
      } else {
        setStep((s) => s + 1);
      }
    }, delay);
    return () => clearTimeout(t);
  }, [replaying, step, rows.length, delay]);

  // 30초 타이머 (고르기 단계에 들어갈 때 한 번 시작)
  useEffect(() => {
    if (stage !== "choose") return undefined;
    const deadline = Date.now() + seconds * 1000;
    const timer = setInterval(() => {
      const left = Math.max(0, (deadline - Date.now()) / 1000);
      setRemaining(left);
      if (left <= 0) {
        clearInterval(timer);
        submit(null);
      }
    }, 200);
    return () => clearInterval(timer);
    // submit은 ref로 한 번만 실행되므로 의존성에 넣지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  function replayAgain() {
    setStep(0);
    setReplaying(true);
  }

  // 지금까지 재생한 조회 기준으로 상품별 조회 수
  const shown = rows.slice(0, step + 1);
  const viewCount = {};
  for (const row of shown) viewCount[row.item_id] = (viewCount[row.item_id] || 0) + 1;
  const current = shown[shown.length - 1];
  const choosing = stage === "choose";
  const urgent = choosing && remaining <= URGENT_SECONDS;

  if (stage === "countdown") {
    return (
      <section className="guess-panel guess-countdown">
        <span className="guess-round-no">
          라운드 {index + 1}/{total}
        </span>
        <span className="guess-level">
          난이도 {"★".repeat(round.level)}
          <span className="guess-level-off">{"★".repeat(3 - round.level)}</span> · 맞히면 {round.level}점
        </span>
        <b key={count} className="guess-count">
          {count || "시작!"}
        </b>
        <p className="guess-hint">손님이 상품을 둘러보는 모습을 먼저 보여드려요.</p>
      </section>
    );
  }

  return (
    <section className="guess-round">
      <header className="guess-round-head">
        <span className="guess-round-no">
          라운드 {index + 1}/{total}
        </span>
        <span className="guess-level">
          난이도 {"★".repeat(round.level)}
          <span className="guess-level-off">{"★".repeat(3 - round.level)}</span> · {round.level}점
        </span>
        <div className={`guess-timer ${urgent ? "is-urgent" : ""} ${choosing ? "" : "is-waiting"}`}>
          <div className="guess-timer-bar">
            <i style={{ width: `${(remaining / seconds) * 100}%` }} />
          </div>
          <b>{choosing ? `${Math.ceil(remaining)}초` : "재생 중"}</b>
        </div>
      </header>

      <div className="guess-panel guess-board-panel">
        <div className="guess-bubble" key={step}>
          🧍 {bubbleText(current, current && productOf[current.item_id])}
        </div>

        <div className="guess-board">
          {round.items.map((item) => {
            const product = productOf[item];
            const views = viewCount[item] || 0;
            const here = current && current.item_id === item && replaying;
            // 많이 본 상품은 재생하는 동안만 빛난다. 고를 때는 👀 숫자만 남겨 선택 표시와 헷갈리지 않게 한다.
            const heat = !replaying ? "" : views >= 3 ? "is-hot" : views === 2 ? "is-warm" : views === 1 ? "is-seen" : "";
            return (
              <button
                key={item}
                className={`guess-card ${heat} ${here ? "is-here" : ""} ${selected === item ? "is-selected" : ""}`}
                onClick={() => setSelected(item)}
                disabled={!choosing || submitting}
              >
                {here && <span className="guess-shopper">🧍</span>}
                <img src={product.image} alt="" />
                <span className="guess-card-name">{productLabel(product)}</span>
                <span className="guess-views">👀 {views}</span>
              </button>
            );
          })}
        </div>

        <ol className="guess-path" aria-label="조회 순서">
          {shown.map((row, i) => (
            <li key={i} className={row.again ? "is-again" : ""}>
              <img src={productOf[row.item_id].image} alt="" />
              <small>{row.gap == null ? "시작" : `+${formatDuration(row.gap)}`}</small>
            </li>
          ))}
        </ol>

        <div className="guess-round-actions">
          <button className="btn guess-btn-outline" onClick={replayAgain} disabled={!choosing || replaying || submitting}>
            ↺ 다시 보기
          </button>
          <span className="guess-ai-status">🤖 AI도 {choosing ? "고르는 중..." : "지켜보는 중..."}</span>
          <button className="btn btn-black guess-decide" disabled={!choosing || selected == null || submitting} onClick={() => submit(selected)}>
            {submitting ? "공개 중..." : choosing ? (selected == null ? "상품을 골라 주세요" : "이걸로 결정!") : "재생이 끝나면 골라요"}
          </button>
        </div>
      </div>
    </section>
  );
}
