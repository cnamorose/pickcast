import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchPeakReplay, fetchPeakResults, fetchPeakWindows } from "../api/peak";
import { BarChart, LineChart, TradeoffChart } from "./charts";
import { leaveTimeline, replayDuration, stateAt, ticksUntil, usePlayback } from "./playback";
import ReplayLane, { scoreLevel } from "./ReplayLane";
import "./peak.css";

// 피크타임 우선 처리 시뮬레이션 화면 (확장 기능 3).
// 쇼핑 체험과 별개라 세션을 만들지 않는다.
// 탭 세 개: 시뮬레이션(같은 장면을 선착순과 우선 처리로 나란히 재생) / 시뮬레이션 결과(지금 장면의 최종 비교)
//          / 전체 결과(100개 시간대). 세 탭 모두 스크롤 없이 한 화면에 맞춘다.

const ALPHAS = [0, 0.5, 1, 2, 5, 10, 20, 50, 100];
const SPEEDS = [1, 2, 4, 8];
// peak.css의 색 변수와 같은 값 (SVG 그래프에 직접 넣어야 해서 여기에도 둔다)
const COLORS = { fifo: "#6b9a4c", priority: "#6f62b8", aging: "#b2302f", left: "#b2302f" };
// 처음 들어왔을 때 보여줄 장면 (0부터 센 번호, 화면에는 4번). 다섯 장면 중 선착순과 차이가 가장 잘 보인다.
// 장면 하나는 예시일 뿐이라 효과 판단은 전체 결과로 하게 안내한다.
const DEFAULT_WINDOW = 3;
const TABS = [
  { id: "sim", label: "시뮬레이션" },
  { id: "scene", label: "시뮬레이션 결과" },
  { id: "overall", label: "전체 결과" },
];

function percent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

// 두 방식의 그래프 두 개 (대기 중인 요청, 떠난 구매 고객). time까지만 그린다.
function LiveCharts({ lanes, leaves, duration, time }) {
  const ticks = {
    fifo: ticksUntil(lanes.fifo, time),
    priority: ticksUntil(lanes.priority, time),
  };
  const until = (name) => leaves[name].filter((p) => p.t <= time);
  const finalMax = (key) => Math.max(1, ...["fifo", "priority"].map((n) => leaves[n].at(-1)?.[key] ?? 0));
  const queueMax = Math.max(
    1,
    ...[lanes.fifo, lanes.priority].flatMap((r) =>
      r ? r.events.filter((e) => e.event === "tick").map((e) => e.queue) : [],
    ),
  );
  const series = (pick) => [
    { name: "선착순", color: COLORS.fifo, points: pick("fifo") },
    { name: "우선 처리", color: COLORS.priority, points: pick("priority") },
  ];
  return (
    <>
      <LineChart
        title="대기 중인 요청"
        xMax={duration}
        xLabel="초"
        yMax={queueMax}
        series={series((n) => ticks[n].map((t) => ({ x: t.t, y: t.queue })))}
      />
      <LineChart
        title="🛒 떠난 구매 고객 (누적)"
        xMax={duration}
        xLabel="초"
        yMax={Math.max(finalMax("buyerLeft"), lanes.fifo?.summary.buyers ?? 1)}
        series={series((n) => until(n).map((p) => ({ x: p.t, y: p.buyerLeft })))}
      />
    </>
  );
}

export default function PeakPage() {
  const [tab, setTab] = useState("sim");
  const [windows, setWindows] = useState([]);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  const [windowIndex, setWindowIndex] = useState(DEFAULT_WINDOW);
  const [policy, setPolicy] = useState("priority");
  const [alphaIndex, setAlphaIndex] = useState(ALPHAS.indexOf(20));
  const [overload, setOverload] = useState(1.5);
  const [speed, setSpeed] = useState(2);
  const [lanes, setLanes] = useState({ fifo: null, priority: null });

  const alpha = ALPHAS[alphaIndex];

  useEffect(() => {
    Promise.all([fetchPeakWindows(), fetchPeakResults()])
      .then(([w, r]) => {
        setWindows(w.windows);
        setResults(r);
      })
      .catch((err) => setError(err.message));
  }, []);

  // 조절값이 바뀌면 같은 장면을 두 방식으로 다시 불러온다. 슬라이더를 움직이는 동안은 잠깐 기다린다.
  useEffect(() => {
    const timer = setTimeout(() => {
      Promise.all([
        fetchPeakReplay({
          window: windowIndex,
          policy: "fifo",
          alpha: 0,
          overload,
        }),
        fetchPeakReplay({ window: windowIndex, policy, alpha, overload }),
      ])
        .then(([fifo, priority]) => setLanes({ fifo, priority }))
        .catch((err) => setError(err.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [windowIndex, policy, alpha, overload]);

  const duration = Math.max(replayDuration(lanes.fifo), replayDuration(lanes.priority));
  const { time, playing, play, pause, reset } = usePlayback(duration, speed);

  // 장면이나 조절값이 바뀌면 처음부터
  useEffect(() => {
    reset();
  }, [lanes, reset]);

  // 왼쪽: 지금까지 들어온 손님 (같은 장면이라 두 방식의 도착은 같다)
  const arrivals = useMemo(() => {
    if (!lanes.fifo) return [];
    return lanes.fifo.events
      .filter((e) => e.event === "arrive" && e.t <= time)
      .slice(-24)
      .reverse();
  }, [lanes.fifo, time]);

  const leaves = useMemo(
    () => ({
      fifo: leaveTimeline(lanes.fifo),
      priority: leaveTimeline(lanes.priority),
    }),
    [lanes],
  );
  const finished = duration > 0 && time >= duration;
  const rightTitle = policy === "aging" ? `우선 처리 + 에이징 (α=${alpha})` : "우선 처리 (확률 높은 순)";
  const scene = windows.find((w) => w.window === windowIndex);

  if (error) {
    return (
      <div className="peak-page">
        <p className="peak-error">{error} — 백엔드 서버가 켜져 있는지 확인해주세요.</p>
        <Link to="/" className="peak-back">
          ← 처음으로
        </Link>
      </div>
    );
  }

  return (
    <div className="peak-page peak-page-fit">
      <header className="peak-topbar">
        <Link to="/" className="peak-back">
          ← 처음으로
        </Link>
        <h1>피크타임 우선 처리 시뮬레이션</h1>
        {tab === "sim" && (
          // 마우스를 올리면 안내 창이 뜬다. 터치 화면에서는 버튼을 누르면(포커스) 뜬다.
          <div className="peak-guide-wrap">
            <button className="peak-guide-toggle">ⓘ 무엇을 보면 되나요?</button>
            <ol className="peak-guide" role="tooltip">
              <li>
                <b>선착순</b>에서는 🛒 구매 고객도 운 나쁘면 기다리다 떠나요.
              </li>
              <li>
                <b>우선 처리</b>는 구매 확률이 높은 고객부터 처리해 🛒 구매 고객을 더 지켜요.
              </li>
              <li>
                대신 확률 낮은(회색) 고객이 더 떠나요. 이 균형은 <b>에이징 α</b>로 조절해요.
              </li>
            </ol>
          </div>
        )}
        <nav className="peak-tabs">
          {TABS.map((t) => (
            <button key={t.id} className={`peak-tab ${tab === t.id ? "is-active" : ""}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {tab === "sim" && (
        <>
          <div className="peak-toolbar">
            <label>
              장면
              <select value={windowIndex} onChange={(e) => setWindowIndex(Number(e.target.value))}>
                {windows.map((w) => (
                  <option key={w.window} value={w.window}>
                    {w.window + 1}번 (구매 {w.buyers}명)
                  </option>
                ))}
              </select>
            </label>
            <div className="peak-field">
              재생 속도
              <div className="peak-buttons">
                {SPEEDS.map((s) => (
                  <button key={s} className={`peak-speed ${s === speed ? "is-active" : ""}`} onClick={() => setSpeed(s)}>
                    x{s}
                  </button>
                ))}
              </div>
            </div>
            <label>
              우선 처리 방식
              <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
                <option value="priority">확률 높은 순</option>
                <option value="aging">확률 + 에이징</option>
              </select>
            </label>
            <label className="peak-slider" title="들어오는 요청이 서버 처리량의 몇 배인지">
              과부하 {overload.toFixed(1)}배
              <input
                type="range"
                min="1"
                max="3"
                step="0.1"
                value={overload}
                onChange={(e) => setOverload(Number(e.target.value))}
              />
            </label>
            <label
              className={`peak-slider ${policy === "aging" ? "" : "is-disabled"}`}
              title="클수록 선착순에 가까워져요"
            >
              α (에이징 세기) {alpha}
              <input
                type="range"
                min="0"
                max={ALPHAS.length - 1}
                value={alphaIndex}
                disabled={policy !== "aging"}
                onChange={(e) => setAlphaIndex(Number(e.target.value))}
              />
            </label>
            {/* 재생 버튼은 오른쪽 끝에 모은다 */}
            <div className="peak-buttons peak-play">
              {playing ? (
                <button className="btn btn-black" onClick={pause}>
                  ⏸ 멈춤
                </button>
              ) : (
                <button className="btn btn-black" onClick={play} disabled={!duration}>
                  ▶ {time > 0 && time < duration ? "이어서" : "재생"}
                </button>
              )}
              <button className="btn peak-btn-outline" onClick={reset}>
                처음으로
              </button>
              {finished && (
                <button className="btn btn-black" onClick={() => setTab("scene")}>
                  결과 보기 →
                </button>
              )}
            </div>
          </div>

          <div className="peak-stage">
            <aside className="peak-arrivals">
              <h3>들어오는 고객</h3>
              <p>숫자는 구매 확률이 평소의 몇 배인지예요. 🛒는 결국 산 고객이에요.</p>
              <ul>
                {arrivals.map((e) => (
                  <li key={e.request} className={`peak-arrival peak-chip-${scoreLevel(e.score)}`}>
                    <span>손님 {e.user}</span>
                    <b>
                      {e.buyer ? "🛒 " : ""}
                      {e.score.toFixed(1)}배
                    </b>
                  </li>
                ))}
              </ul>
            </aside>

            <ReplayLane variant="fifo" title="선착순" subtitle="먼저 온 고객부터" replay={lanes.fifo} time={time} />
            <ReplayLane
              variant="priority"
              title={rightTitle}
              subtitle="왼쪽부터 다음 처리 순서"
              replay={lanes.priority}
              time={time}
            />

            <aside className="peak-live">
              {/* 두 그래프가 같은 범례를 쓰므로 맨 위 한 줄에 범례와 재생 시간을 모은다 */}
              <div className="peak-live-head">
                <h3>그래프</h3>
                <span className="peak-legend">
                  <span>
                    <i style={{ background: COLORS.fifo }} />
                    선착순
                  </span>
                  <span>
                    <i style={{ background: COLORS.priority }} />
                    우선 처리
                  </span>
                </span>
                <span className="peak-clock">
                  {time.toFixed(0)}초 / {duration.toFixed(0)}초
                </span>
              </div>
              <LiveCharts lanes={lanes} leaves={leaves} duration={duration} time={time} />
            </aside>
          </div>
        </>
      )}

      {tab === "scene" && (
        <SceneResult
          lanes={lanes}
          leaves={leaves}
          duration={duration}
          scene={scene}
          rightTitle={rightTitle}
          overload={overload}
          overall={results && overallFor(results, policy, alpha)}
          overallBuyers={results?.test.fifo.buyers}
          overallFifo={results?.test.fifo}
          overallOverload={results?.settings.overload}
          onOverall={() => setTab("overall")}
          onBack={() => setTab("sim")}
        />
      )}

      {tab === "overall" && results && <OverallResults results={results} />}

      <p className="peak-attribution">데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)</p>
    </div>
  );
}

// 지금 장면을 끝까지 돌렸을 때 두 방식이 무엇을 맞바꿨는지 (재생을 끝까지 보지 않아도 계산할 수 있다)
// 화면에서 고른 방식·α와 같은 설정의 100개 시간대 결과 (없으면 null)
function overallFor(results, policy, alpha) {
  if (policy === "priority" || alpha === 0) return results.test.priority;
  const curve = results.test_alpha_curve ?? [];
  return curve.find((r) => r.policy === "aging" && r.alpha === alpha) ?? null;
}

// 비율 × 전체 구매 고객 수 = 지킨 사람 수 (비율이 사람 수로 계산된 값이라 반올림하면 정확히 돌아온다)
function buyersKept(row, buyers) {
  return Math.round(row.protected_buyer_rate * buyers);
}

function SceneResult({
  lanes,
  leaves,
  duration,
  scene,
  rightTitle,
  overload,
  overall,
  overallBuyers,
  overallFifo,
  overallOverload,
  onOverall,
  onBack,
}) {
  if (!lanes.fifo || !lanes.priority) return <p className="peak-loading">불러오는 중...</p>;
  const fifo = stateAt(lanes.fifo, duration);
  const priority = stateAt(lanes.priority, duration);
  const kept = priority.protectedBuyers - fifo.protectedBuyers;
  const extraLow = priority.lowLeft - fifo.lowLeft;
  const keptText =
    kept > 0
      ? `구매 고객을 ${kept}명 더 지켰고`
      : kept < 0
        ? `구매 고객을 ${-kept}명 덜 지켰고`
        : "구매 고객은 같은 수만큼 지켰고";
  const lowText =
    extraLow > 0
      ? `확률 낮은 고객은 ${extraLow}명 더 떠났어요`
      : extraLow < 0
        ? `확률 낮은 고객은 ${-extraLow}명 덜 떠났어요`
        : "확률 낮은 고객 이탈은 같았어요";
  // higher: 클수록 좋은 지표인지 (차이 배지 색을 정한다). total: 막대의 기준 (없으면 두 값 중 큰 값)
  const metrics = [
    { label: "🛒 지킨 구매 고객", unit: "명", fifo: fifo.protectedBuyers, priority: priority.protectedBuyers, higher: true, total: fifo.buyers },
    { label: "떠난 고객", unit: "명", fifo: fifo.left, priority: priority.left, higher: false },
    { label: "떠난 확률 낮은 고객", unit: "명", fifo: fifo.lowLeft, priority: priority.lowLeft, higher: false },
    { label: "처리한 요청", unit: "건", fifo: fifo.served, priority: priority.served, higher: true },
  ];

  return (
    <section className="peak-overall">
      <h2>
        시뮬레이션 결과 ({scene ? `${scene.window + 1}번 장면` : "지금 장면"}, 과부하 {overload.toFixed(1)}배)
      </h2>
      <p>
        이 장면에서 {rightTitle}는 선착순보다 <b>{keptText}</b>, <b>{lowText}</b>.
      </p>
      <div className="peak-metrics">
        {metrics.map((m) => {
          const diff = m.priority - m.fifo;
          const suffix = m.total != null ? `/${m.total}` : "";
          return (
            <MetricCard
              key={m.label}
              label={m.label}
              badge={{ text: diff === 0 ? "차이 없음" : `${diff > 0 ? "+" : ""}${diff}${m.unit}`, tone: diffTone(diff, m.higher) }}
              base={Math.max(1, m.total ?? Math.max(m.fifo, m.priority))}
              rows={[
                { name: "선착순", value: m.fifo, color: COLORS.fifo, text: `${m.fifo}${suffix}` },
                { name: "우선 처리", value: m.priority, color: COLORS.priority, text: `${m.priority}${suffix}` },
              ]}
            />
          );
        })}
      </div>
      <div className="peak-scene-charts">
        <LiveCharts lanes={lanes} leaves={leaves} duration={duration} time={duration} />
      </div>
      <p className="peak-compare">
        {overload !== overallOverload ? (
          <>전체 결과는 과부하 {overallOverload}배 기준이라, 과부하를 바꾼 이 장면과는 비교하지 않아요.</>
        ) : overall && overallFifo ? (
          <>
            📊 같은 설정으로 붐비는 시간대 100개를 모두 돌리면, 구매 고객 {overallBuyers}명 중 선착순은{" "}
            <b>{buyersKept(overallFifo, overallBuyers)}명</b>, 이 방식은 <b>{buyersKept(overall, overallBuyers)}명</b>을
            지켜요 ({((overall.protected_buyer_rate - overallFifo.protected_buyer_rate) * 100).toFixed(1)}%p). 장면
            하나에는 구매 고객이 7~8명뿐이라 들쭉날쭉하니, 효과는 이 숫자로 판단해주세요.
          </>
        ) : (
          <>장면 하나에는 구매 고객이 7~8명뿐이라 결과가 들쭉날쭉해요. 효과는 전체 결과로 판단해주세요.</>
        )}
      </p>
      <div className="peak-buttons">
        <button className="btn btn-black" onClick={onOverall}>
          전체 결과 보기 →
        </button>
        <button className="btn peak-btn-outline" onClick={onBack}>
          시뮬레이션으로
        </button>
      </div>
    </section>
  );
}

// 지표 하나를 방식별 막대와 차이 배지로 보여준다. rows: [{ name, value, color, text }], base: 막대 100%의 값
function MetricCard({ label, badge, rows, base }) {
  return (
    <div className="peak-metric">
      <div className="peak-metric-head">
        <span>{label}</span>
        {badge && <em className={badge.tone ? `is-${badge.tone}` : ""}>{badge.text}</em>}
      </div>
      {rows.map((r) => (
        <div key={r.name} className="peak-metric-row">
          <span className="peak-metric-name">{r.name}</span>
          <div className="peak-metric-bar">
            <i style={{ width: `${(r.value / base) * 100}%`, background: r.color }} />
          </div>
          <b>{r.text}</b>
        </div>
      ))}
    </div>
  );
}

// 우선 처리 쪽이 선착순보다 좋아졌는지에 따라 배지 색을 정한다. higher: 클수록 좋은 지표인지
function diffTone(diff, higher) {
  if (diff === 0) return null;
  return diff > 0 === higher ? "better" : "worse";
}

// 100개 시간대 전체 결과 (test)
function OverallResults({ results }) {
  const { fifo, priority, aging } = results.test;
  const chosen = results.settings.chosen_alpha;
  const curve = results.test_alpha_curve ?? results.valid_alpha_curve;
  const policies = [
    ["선착순", fifo, COLORS.fifo],
    ["확률 우선", priority, COLORS.priority],
    [`에이징 α=${chosen}`, aging, COLORS.aging],
  ];
  // 실험 조건: 숫자가 어떤 조건에서 나왔는지 (모두 결과 파일의 settings 값)
  const { settings } = results;
  const conditions = [
    `붐비는 시간대 ${settings.windows}개 (test 구간, 고객 ${fifo.users.toLocaleString()}명)`,
    `1시간을 ${settings.compressed_seconds_per_hour}초로 압축`,
    `과부하 ${settings.overload}배`,
    `${settings.timeout_seconds}초 넘게 기다리면 떠남`,
    `구매 확률 모델 ${settings.model_version}`,
    `α는 valid 구간에서 미리 정한 기준으로 선택`,
  ];
  // 배지는 미리 정한 기준으로 고른 에이징이 선착순보다 얼마나 달라졌는지 보여준다
  const overallMetrics = [
    { key: "protected_buyer_rate", label: "🛒 지킨 구매 고객", higher: true },
    { key: "low_left_rate", label: "확률 낮은 고객 이탈", higher: false },
    { key: "left_rate", label: "전체 이탈", higher: false },
  ];

  const groups = [
    { label: "선착순", row: fifo },
    { label: "확률 우선", row: priority },
    { label: `에이징 α=${chosen}`, row: aging },
  ].map(({ label, row }) => ({
    label,
    values: [
      {
        name: "지킨 구매 고객",
        value: row.protected_buyer_rate,
        color: COLORS.priority,
      },
      {
        name: "확률 낮은 고객 이탈",
        value: row.low_left_rate,
        color: COLORS.left,
      },
    ],
  }));

  const points = curve.map((r) => ({
    x: r.low_left_rate,
    y: r.protected_buyer_rate,
    fifo: r.policy === "fifo",
    highlight: r.policy !== "fifo" && r.alpha === chosen,
    label: r.policy === "fifo" ? "선착순" : r.alpha === chosen ? `선택 α=${chosen}` : `α=${r.alpha}`,
  }));

  return (
    <section className="peak-overall">
      <h2>전체 결과 (붐비는 시간대 100개, test)</h2>
      <p>
        미리 정한 기준(확률 낮은 고객 이탈이 선착순보다 5%p 넘게 늘지 않음)으로 고른 α={chosen}은 선착순보다 구매 고객을{" "}
        <b>
          {((aging.protected_buyer_rate - fifo.protected_buyer_rate) * 100).toFixed(1)}
          %p
        </b>{" "}
        더 지키고, 확률 낮은 고객 이탈은 <b>{((aging.low_left_rate - fifo.low_left_rate) * 100).toFixed(1)}%p</b>{" "}
        늘었어요. 구매 고객 {fifo.buyers}명으로 보면 선착순 <b>{buyersKept(fifo, fifo.buyers)}명</b>, 확률 우선{" "}
        <b>{buyersKept(priority, fifo.buyers)}명</b>, 에이징 α={chosen} <b>{buyersKept(aging, fifo.buyers)}명</b>을 지켰어요.
      </p>
      <ul className="peak-conditions">
        {conditions.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
      <div className="peak-overall-charts">
        <BarChart title="방식별 결과" groups={groups} />
        <TradeoffChart title="맞바꾸는 관계 (α를 바꾸면)" points={points} />
      </div>
      <div className="peak-metrics peak-metrics-3">
        {overallMetrics.map((m) => {
          const diff = aging[m.key] - fifo[m.key];
          return (
            <MetricCard
              key={m.key}
              label={m.label}
              badge={{ text: `α=${chosen}: ${diff > 0 ? "+" : ""}${(diff * 100).toFixed(1)}%p`, tone: diffTone(diff, m.higher) }}
              base={1}
              rows={policies.map(([name, row, color]) => ({ name, value: row[m.key], color, text: percent(row[m.key]) }))}
            />
          );
        })}
      </div>
      <p className="peak-caveat">
        "처리만 되면 원래대로 샀을 것"이라는 가정 위의 시뮬레이션이에요. 실제 효과는 A/B 테스트로 확인해야 해요. 확률은
        조회 행동만으로 계산하고 개인 정보는 쓰지 않아요.
      </p>
    </section>
  );
}
