import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDashboard } from "../api/session";
import { getProduct, CATEGORIES, CATEGORY_LABELS } from "../data/products";
import "./dashboard.css";

// 판매자 대시보드 (확장 기능 2).
// GET /dashboard 를 몇 초마다 불러서 "지금 쇼핑 중인 고객" 기준의 상품별 구매 가능성,
// 단계별 인원, 자주 비교되는 상품 쌍, 확인해볼 점(insights)을 보여준다.
// 상품별 지표는 at_least_one(1명 이상 살 확률)을 중심으로 쓴다. 예상 구매 수는 대부분 0.1개 미만이라 보조로만 쓴다.

const REFRESH_MS = 5000;

const STAGES = [
  { key: "decided", label: "살 마음 먹음", color: "#c8553d" },
  { key: "comparing", label: "고민 중", color: "#3a7ca5" },
  { key: "leaving", label: "떠나려는 중", color: "#d9a441" },
  { key: "browsing", label: "구경 중", color: "#b9b5ad" },
];

const INSIGHT_LABELS = {
  low_stock: { label: "재고 확인", tone: "warn" },
  comparing_pair: { label: "함께 고민", tone: "info" },
  weak_intent: { label: "관심 대비 반응 약함", tone: "muted" },
  leaving: { label: "이탈 조짐", tone: "warn" },
  too_few_sessions: { label: "안내", tone: "muted" },
};

function percent(value) {
  if (!value) return "0%";
  if (value < 0.001) return "<0.1%";
  return `${(value * 100).toFixed(1)}%`;
}

function timeText(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleTimeString("ko-KR", { hour12: false });
}

function Thumb({ id, size = 40 }) {
  const p = getProduct(id);
  return (
    <img
      className="dash-thumb"
      src={p?.image}
      alt={id}
      style={{ width: size, height: Math.round(size * 1.25) }}
    />
  );
}

function StageSummary({ stages, total }) {
  const sum = STAGES.reduce((acc, s) => acc + (stages?.[s.key] || 0), 0);
  return (
    <section className="dash-card dash-stages">
      <div className="dash-card-head">
        <h2>쇼핑 중 고객의 구매 의도</h2>
        <span className="dash-muted">총 {total}명</span>
      </div>
      <div className="dash-stage-tiles">
        {STAGES.map((s) => (
          <div className="dash-stage-tile" key={s.key}>
            <span className="dash-dot" style={{ background: s.color }} />
            <span className="dash-stage-label">{s.label}</span>
            <b>{stages?.[s.key] || 0}</b>
          </div>
        ))}
      </div>
      <div className="dash-stack" aria-hidden="true">
        {sum > 0 &&
          STAGES.map((s) =>
            stages?.[s.key] ? (
              <span key={s.key} style={{ width: `${(stages[s.key] / sum) * 100}%`, background: s.color }} />
            ) : null
          )}
      </div>
    </section>
  );
}

function Insights({ insights }) {
  if (!insights?.length) return null;
  return (
    <section className="dash-card">
      <div className="dash-card-head">
        <h2>확인해볼 점</h2>
        <span className="dash-muted">규칙 기반 안내 · 원인은 추측하지 않아요</span>
      </div>
      <ul className="dash-insights">
        {insights.map((it, i) => {
          const meta = INSIGHT_LABELS[it.type] || { label: "안내", tone: "muted" };
          return (
            <li key={i} className={`dash-insight dash-tone-${meta.tone}`}>
              <span className="dash-insight-tag">{meta.label}</span>
              <p>{it.message}</p>
              {it.items?.length > 0 && (
                <div className="dash-insight-items">
                  {it.items.map((id) => (
                    <Thumb key={id} id={id} size={28} />
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ComparePairs({ pairs }) {
  return (
    <section className="dash-card">
      <div className="dash-card-head">
        <h2>자주 비교되는 상품</h2>
        <span className="dash-muted">고민 중 고객 기준</span>
      </div>
      {!pairs?.length ? (
        <p className="dash-empty-small">아직 함께 고민 중인 상품이 없어요.</p>
      ) : (
        <ol className="dash-pairs">
          {pairs.map((pair, i) => (
            <li key={pair.items.join("-")}>
              <span className="dash-rank">{i + 1}</span>
              <div className="dash-pair-items">
                {pair.items.map((id) => (
                  <div key={id} className="dash-pair-item">
                    <Thumb id={id} size={34} />
                    <span>{id}</span>
                  </div>
                ))}
              </div>
              <b className="dash-pair-count">{pair.sessions}명</b>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function ProductTable({ products }) {
  const [category, setCategory] = useState("ALL");
  const [onlyViewed, setOnlyViewed] = useState(true);
  const [showAll, setShowAll] = useState(false);

  const rows = useMemo(() => {
    return (products || [])
      .filter((p) => category === "ALL" || p.item_id.startsWith(`${category}-`))
      .filter((p) => !onlyViewed || p.viewers > 0)
      .sort((a, b) => b.at_least_one - a.at_least_one || b.viewers - a.viewers);
  }, [products, category, onlyViewed]);

  const maxProb = Math.max(0.0001, ...rows.map((r) => r.at_least_one));
  // 기본은 상위 10개만 보여주고, 버튼으로 전체를 펼친다.
  const TOP_N = 10;
  const visible = showAll ? rows : rows.slice(0, TOP_N);

  return (
    <section className="dash-card dash-products">
      <div className="dash-card-head">
        <h2>지금 팔릴 가능성이 높은 상품</h2>
        <label className="dash-toggle">
          <input type="checkbox" checked={onlyViewed} onChange={(e) => setOnlyViewed(e.target.checked)} />
          보는 고객이 있는 상품만
        </label>
      </div>

      <div className="dash-tabs">
        {["ALL", ...CATEGORIES].map((c) => (
          <button
            key={c}
            className={`dash-tab ${category === c ? "dash-tab-active" : ""}`}
            onClick={() => setCategory(c)}
          >
            {c === "ALL" ? "전체" : CATEGORY_LABELS[c]}
          </button>
        ))}
      </div>

      {rows.length === 0 ? (
        <p className="dash-empty-small">조건에 맞는 상품이 없어요.</p>
      ) : (
        <div className="dash-table-wrap">
          <table className="dash-table">
            <thead>
              <tr>
                <th>상품</th>
                <th className="num">보는 고객</th>
                <th className="dash-col-prob">1명 이상 살 확률</th>
                <th className="num">예상 구매 (90% 범위)</th>
                <th className="num">결제 수</th>
                <th className="num">남은 재고</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => {
                const p = getProduct(r.item_id);
                const left = r.stock - r.purchased;
                return (
                  <tr key={r.item_id}>
                    <td>
                      <div className="dash-product">
                        <Thumb id={r.item_id} size={36} />
                        <div>
                          <b>{r.item_id}</b>
                          <span>{p ? `${p.type} · ${p.color}` : ""}</span>
                        </div>
                      </div>
                    </td>
                    <td className="num">{r.viewers}명</td>
                    <td className="dash-col-prob">
                      <div className="dash-prob">
                        <div className="dash-bar">
                          <span style={{ width: `${(r.at_least_one / maxProb) * 100}%` }} />
                        </div>
                        <b>{percent(r.at_least_one)}</b>
                      </div>
                    </td>
                    <td className="num dash-muted">
                      {r.expected.toFixed(2)}개 ({r.low}~{r.high})
                    </td>
                    <td className="num">{r.purchased}</td>
                    <td className="num">
                      {left <= 0 ? (
                        <span className="dash-badge dash-badge-out">품절</span>
                      ) : left <= 1 ? (
                        <span className="dash-badge dash-badge-low">{left}개</span>
                      ) : (
                        `${left}개`
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length > TOP_N && (
            <button className="dash-more" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "상위 10개만 보기" : `전체 ${rows.length}개 보기`}
            </button>
          )}
        </div>
      )}
      <p className="dash-footnote">
        예상 구매 수는 "지금 보는 고객 중 결국 몇 명이 살지"이며 기간 단위(오늘 몇 개)가 아니에요. 재고는 데모용
        가상 데이터예요.
      </p>
    </section>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [paused, setPaused] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await fetchDashboard();
      setData(next);
      setError(null);
    } catch (err) {
      setError(err.message || "대시보드를 불러오지 못했어요.");
    }
  }, []);

  useEffect(() => {
    load();
    if (paused) return undefined;
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load, paused]);

  return (
    <div className="dash-page">
      <header className="dash-topbar">
        <div>
          <h1>판매자 대시보드</h1>
          <p className="dash-muted">
            최근 {data?.active_window_minutes ?? 30}분 안에 상품을 본 <b>쇼핑 중 고객</b> 기준 · AI 구매 예측
          </p>
        </div>
        <div className="dash-topbar-right">
          <span className={`dash-live ${paused || error ? "dash-live-off" : ""}`}>
            {paused ? "일시정지" : error ? "연결 안 됨" : "실시간"}
          </span>
          <span className="dash-muted">마지막 갱신 {timeText(data?.generated_at)}</span>
          <button className="dash-btn" onClick={() => setPaused((v) => !v)}>
            {paused ? "다시 갱신" : "일시정지"}
          </button>
          <Link to="/" className="dash-btn">
            처음으로
          </Link>
        </div>
      </header>

      {error && !data && (
        <div className="dash-empty">
          <b>대시보드를 불러오지 못했어요.</b>
          <p>백엔드 서버가 켜져 있는지 확인해주세요. ({error})</p>
        </div>
      )}

      {data && (
        <>
          {data.active_sessions === 0 && (
            <div className="dash-empty">
              <b>지금 쇼핑 중인 고객이 없어요.</b>
              <p>
                체험을 시작하거나, 테스트용 가상 손님을 만들어보세요:{" "}
                <code>python backend/scripts/seed_dashboard.py --shoppers 60</code>
              </p>
            </div>
          )}

          <div className="dash-grid">
            <div className="dash-main">
              <StageSummary stages={data.stages} total={data.active_sessions} />
              <ProductTable products={data.products} />
            </div>
            <aside className="dash-side">
              <Insights insights={data.insights} />
              <ComparePairs pairs={data.compare_pairs} />
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
