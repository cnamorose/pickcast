import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fetchJourney, fetchJourneys, fetchStore } from "../api/journeys";
import CustomerMonitor from "./CustomerMonitor";
import SellerDashboard from "./SellerDashboard";
import { assignFeatured, clockText, customerState, customerTopic, durationText, narrate, percent } from "./simData";
import "./simulation.css";

// 판매 시뮬레이션: 학습에 쓰지 않은 2015년 8월 실제 쇼핑몰의 붐비는 두 시간을 같은 시계로 재생한다.
// 왼쪽은 손님이 보는 컴퓨터 화면(손님 탭), 오른쪽은 가게 전체를 보는 판매자 관리자 화면이고,
// 가운데 자막이 손님의 행동과 AI 예측을 한 문장으로 잇는다. 처음 들어오면 설명 화면을 먼저 보여준다.

// 실제 1초에 흐르는 시뮬레이션 초
const SPEEDS = [
  { label: "천천히", value: 30 },
  { label: "보통", value: 60 },
  { label: "빠르게", value: 180 },
];
// 처음 볼 시각: 첫 손님이 들어오기 조금 전 (시간 창 시작부터 25분)
const START_SECOND = 25 * 60;
// 탭 손님이 행동하는 순간 잠깐 멈춰 보여주는 시간(ms)
const HOLD_MS = { view: 1200, addtocart: 2800, transaction: 3200 };

export default function SimulationPage() {
  const [summary, setSummary] = useState(null);
  const [store, setStore] = useState(null);
  const [journeys, setJourneys] = useState(null);
  const [error, setError] = useState(null);
  const [guide, setGuide] = useState(true);
  const [t, setT] = useState(START_SECOND);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(60);
  const [manual, setManual] = useState(1);
  const [auto, setAuto] = useState(true);

  useEffect(() => {
    Promise.all([fetchJourneys(), fetchStore()])
      .then(async ([list, storeData]) => {
        const full = await Promise.all(list.customers.map((c) => fetchJourney(c.id)));
        // 탭 손님들이 본 상품에는 서로 다른 그림을 붙인다 (판매자 화면도 같은 그림을 쓴다).
        assignFeatured(full.flatMap((j) => j.steps.map((s) => s.item_id)));
        setSummary(list);
        setStore(storeData);
        setJourneys(full);
      })
      .catch((err) => setError(err.message));
  }, []);

  const duration = summary ? summary.window.minutes * 60 : 0;
  // 탭 손님들의 행동 시각 (재생 중 이 시각을 지나면 잠깐 멈춘다)
  const actions = useMemo(
    () => (journeys ? journeys.flatMap((j) => j.steps.map((s) => ({ second: s.second, event: s.event }))).sort((a, b) => a.second - b.second) : []),
    [journeys]
  );

  // 재생: requestAnimationFrame으로 시각을 흘리고, 탭 손님이 행동하는 시각에서 잠깐 멈춘다.
  const exact = useRef(t);
  useEffect(() => {
    exact.current = t;
  }, [t]);
  useEffect(() => {
    if (!playing || !duration) return undefined;
    let frame;
    let last = null;
    let holdUntil = 0;
    const tick = (now) => {
      if (last != null && now >= holdUntil) {
        const from = exact.current;
        let next = Math.min(duration, from + ((now - last) / 1000) * speed);
        const hit = actions.find((a) => a.second > from && a.second <= next);
        if (hit) {
          next = hit.second;
          holdUntil = now + HOLD_MS[hit.event];
        }
        exact.current = next;
        setT(next);
        if (next >= duration) {
          setPlaying(false);
          return;
        }
      }
      last = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, duration, actions]);

  if (error) {
    return (
      <div className="sim-page">
        <p className="sim-message">데이터를 불러오지 못했어요: {error}</p>
        <Link to="/" className="sim-back">
          ← 처음으로
        </Link>
      </div>
    );
  }

  const ready = summary && store && journeys;
  // 자동으로 따라가기: 탭 손님 중 가장 최근에 행동한 손님을 보여준다.
  let selected = manual;
  if (ready && auto) {
    let latest = null;
    for (const j of journeys) {
      const s = customerState(j, t);
      if (s.status === "shopping" && (!latest || j.steps[s.index].second > latest.second)) {
        latest = { id: j.id, second: j.steps[s.index].second };
      }
    }
    if (latest) selected = latest.id;
  }

  function seek(value) {
    exact.current = value;
    setT(value);
  }

  return (
    <div className="sim-page">
      <div className="sim-container">
        {/* 한 화면에 다 들어가도록 제목·재생 조작·시계를 한 줄에 둔다 */}
        <header className="sim-topbar" aria-label="재생 조작">
          <Link to="/" className="sim-back">
            ←
          </Link>
          <div className="sim-title">
            <h1>판매 시뮬레이션</h1>
            <p>손님들이 쇼핑하는 동안, 판매자는 AI로 무엇을 미리 알 수 있을까요?</p>
          </div>
          <button className="sim-play" onClick={() => setPlaying((p) => !p)} disabled={!ready}>
            {playing ? "❚❚ 잠깐 멈춤" : "▶ 재생"}
          </button>
          <div className="sim-speeds" role="group" aria-label="재생 속도">
            {SPEEDS.map((s) => (
              <button key={s.value} className={s.value === speed ? "sim-chip sim-chip-on" : "sim-chip"} onClick={() => setSpeed(s.value)}>
                {s.label}
              </button>
            ))}
          </div>
          <input
            className="sim-slider"
            type="range"
            min={0}
            max={duration || 1}
            step={10}
            value={t}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label="재생 시각"
            disabled={!ready}
          />
          <span className="sim-clock">{ready ? clockText(summary.window, t) : "--:--"}</span>
          <button
            className="sim-help"
            onClick={() => {
              setPlaying(false);
              setGuide(true);
            }}
          >
            ? 보는 법
          </button>
        </header>

        {!ready ? (
          <p className="sim-message">기록을 불러오는 중이에요…</p>
        ) : (
          <>
            <Caption journeys={journeys} selected={selected} t={t} window={summary.window} />
            <div className="sim-split">
              <CustomerMonitor
                journeys={journeys}
                selected={selected}
                onSelect={(id) => {
                  setManual(id);
                  setAuto(false);
                }}
                auto={auto}
                onToggleAuto={() => {
                  setManual(selected);
                  setAuto((a) => !a);
                }}
                t={t}
                window={summary.window}
                threshold={journeys[0].threshold}
              />
              <SellerDashboard store={store} journeys={journeys} selected={selected} t={t} window={summary.window} />
            </div>
          </>
        )}

        <p className="sim-footnote">
          2015년 8월 실제 쇼핑몰 기록(AI가 학습하지 않은 기간) · 손님 6명은 무작위로 골랐고, 판매자 화면은 이 시간 손님 전체(최대 약
          500명)를 합친 결과 · 상품 그림은 임의로 붙였고 재고는 가정한 값 · 시각은 데이터 기준(UTC)
        </p>
      </div>

      {guide && (
        <Guide
          ready={Boolean(ready)}
          onStart={() => {
            setGuide(false);
            setPlaying(true);
          }}
        />
      )}
    </div>
  );
}

function Caption({ journeys, selected, t, window }) {
  const journey = journeys.find((j) => j.id === selected);
  const state = customerState(journey, t);
  if (state.status !== "shopping") {
    return (
      <section className="sim-caption">
        <span className="sim-caption-icon">{state.status === "waiting" ? "⏳" : "👋"}</span>
        <div>
          <strong>
            {state.status === "waiting"
              ? `${customerTopic(journey.id)} ${clockText(window, t + state.enterIn)}에 들어와요 (${durationText(state.enterIn)} 뒤)`
              : `${customerTopic(journey.id)} 쇼핑을 마쳤어요`}
          </strong>
          <span>오른쪽 판매자 화면에서는 다른 손님들의 쇼핑이 계속 반영되고 있어요.</span>
        </div>
      </section>
    );
  }
  const story = narrate(journey, state.index);
  return (
    <section key={`${journey.id}-${state.index}`} className={story.key ? "sim-caption sim-caption-key" : "sim-caption"} aria-live="polite">
      <span className="sim-caption-icon">{story.icon}</span>
      <div>
        <strong>{story.customer}</strong>
        <span>
          {story.ai}
          {story.to != null && (
            <em>
              {" "}
              (살 가능성 {story.from != null ? `${percent(story.from)} → ` : ""}
              <b>{percent(story.to)}</b>)
            </em>
          )}
        </span>
      </div>
    </section>
  );
}

function Guide({ ready, onStart }) {
  return (
    <div className="sim-guide-backdrop" role="dialog" aria-modal="true" aria-labelledby="sim-guide-title">
      <div className="sim-guide">
        <h2 id="sim-guide-title">이 화면은 이렇게 봐요</h2>
        <ol>
          <li>
            <b>1</b>
            <div>
              <strong>실제 쇼핑몰의 붐비는 두 시간을 그대로 다시 보여줘요</strong>
              <span>2015년 실제 쇼핑몰 기록이에요. AI가 공부할 때 보지 않은 기간이라 AI도 처음 보는 손님들이에요.</span>
            </div>
          </li>
          <li>
            <b>2</b>
            <div>
              <strong>왼쪽은 손님의 컴퓨터 화면, 오른쪽은 판매자의 관리자 화면이에요</strong>
              <span>왼쪽 위 탭으로 손님 1~6을 골라 볼 수 있어요. 처음에는 지금 움직이는 손님을 자동으로 따라가요.</span>
            </div>
          </li>
          <li>
            <b>3</b>
            <div>
              <strong>판매자는 가게 전체 손님의 예측을 모아 봐요</strong>
              <span>곧 팔릴 상품과 재고가 모자랄 상품을 미리 알려줘요. 손님이 나가면 AI가 맞혔는지도 확인해 보세요.</span>
            </div>
          </li>
        </ol>
        <button className="sim-play sim-guide-start" onClick={onStart} disabled={!ready}>
          {ready ? "▶ 시작하기" : "불러오는 중…"}
        </button>
      </div>
    </div>
  );
}
