import { clockText, customerState, percent, productFor, productName, reasonSentence, verdict } from "./simData";

// 오른쪽: 판매자가 켜 둔 관리자 프로그램. 가게 전체 손님의 예측을 모아
// 곧 팔릴 상품, 가정 재고와 알림, 방금 팔린 상품, 지금 고른 손님의 관심 상품을 보여준다.
// 한 화면에 다 들어가도록 상품은 7개, 판매는 4건, 알림은 한 줄만 보여준다.

const STATUS_TEXT = { refill: "채우세요", soldout: "품절", ok: "충분" };
const SOLD_HIGHLIGHT_SECONDS = 5 * 60;
const SHOWN_ITEMS = 7;
const SHOWN_SALES = 4;
const SHOWN_WATCHING = 3;

export default function SellerDashboard({ store, journeys, selected, t, window }) {
  const k = Math.min(store.minutes - 1, Math.max(0, Math.floor(t / 60)));
  const columns = Object.fromEntries(store.top_item_columns.map((name, i) => [name, i]));
  const allItems = store.top_items[k].map((r) => ({
    item: r[columns.item],
    chance: r[columns.at_least_one],
    customers: r[columns.customers],
    stock: r[columns.stock_left],
    status: r[columns.status],
  }));
  const items = allItems.slice(0, SHOWN_ITEMS);
  const alerts = allItems.filter((i) => i.status !== "ok");
  const salesSoFar = store.sales.filter((s) => s.second <= t);
  const recentlySold = new Set(salesSoFar.filter((s) => s.second > t - SOLD_HIGHLIGHT_SECONDS).map((s) => s.item_id));

  // 탭 손님이 지금 관심 있는 상품 (가게 전체 표에서도 표시)
  const journey = journeys.find((j) => j.id === selected);
  const state = customerState(journey, t);
  const watching = state.status === "shopping" ? journey.steps[state.index].dashboard.candidates : [];
  const watchingItems = new Set(watching.map((c) => c.item_id));

  return (
    <section className="sim-admin" aria-label="판매자가 보는 화면">
      <aside className="sim-admin-side">
        <div className="sim-admin-brand">
          <b>Pickcast</b>
          <span>판매자 센터</span>
        </div>
        <nav>
          <span className="sim-admin-menu sim-admin-menu-on">📊 실시간</span>
          <span className="sim-admin-menu">📦 상품</span>
          <span className="sim-admin-menu">🧾 주문</span>
          <span className="sim-admin-menu">🏷 재고</span>
        </nav>
        <small className="sim-admin-model">AI 모델 v3</small>
      </aside>

      <div className="sim-admin-main">
        <header className="sim-admin-top">
          <span className="sim-section-badge sim-section-badge-dark">🧑‍💼 판매자가 보는 화면</span>
          <span className="sim-admin-clock">
            <span className="sim-live" /> {clockText(window, t)} <small>UTC</small>
          </span>
        </header>

        <div className="sim-kpis">
          <Kpi label="쇼핑 중인 손님" value={`${store.shoppers[k]}명`} />
          <Kpi label="장바구니 손님" value={`${store.carting[k]}명`} />
          <Kpi label="앞으로 10분 예상 판매" value={`${store.expected_next_10m[k].toFixed(1)}개`} accent />
          <Kpi label="이 시간대 판매" value={`${salesSoFar.length}건`} />
        </div>

        <Alert alerts={alerts} />

        <div className="sim-admin-grid">
          <div className="sim-card">
            <h3>
              곧 팔릴 상품 <small>10분 기준 · 재고는 가정값</small>
            </h3>
            <table className="sim-table">
              <thead>
                <tr>
                  <th>상품</th>
                  <th>팔릴 확률</th>
                  <th>보는 손님</th>
                  <th>재고</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr
                    key={row.item}
                    className={[
                      recentlySold.has(row.item) ? "sim-row-sold" : "",
                      watchingItems.has(row.item) ? "sim-row-watch" : "",
                    ].join(" ")}
                  >
                    <td>
                      {/* td에 직접 flex를 주면 표 칸이 깨지므로 안쪽 상자에 준다 */}
                      <div className="sim-table-product">
                        <img src={productFor(row.item).image} alt="" />
                        <span>
                          {productName(row.item)}
                          {watchingItems.has(row.item) && <em className="sim-tag sim-tag-watch">손님 {selected}</em>}
                          {recentlySold.has(row.item) && <em className="sim-tag sim-tag-sold">방금 팔림</em>}
                        </span>
                      </div>
                    </td>
                    <td>{percent(row.chance, 0)}</td>
                    <td>{row.customers}명</td>
                    <td>
                      <span className={`sim-status sim-status-${row.status}`}>
                        {row.stock}개{row.status !== "ok" ? ` · ${STATUS_TEXT[row.status]}` : ""}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="sim-side-cards">
            <div className="sim-card">
              <h3>예상 vs 실제 판매 <small>10분마다</small></h3>
              <Chart store={store} t={t} />
            </div>
            <div className="sim-card">
              <h3>방금 팔린 상품</h3>
              <ol className="sim-sales">
                {salesSoFar.slice(-SHOWN_SALES).reverse().map((s) => (
                  <li key={`${s.second}-${s.item_id}`}>
                    <img src={productFor(s.item_id).image} alt="" />
                    <span>
                      <b>{clockText(window, s.second)}</b> {productName(s.item_id)}
                      <small>{s.rank == null ? "AI가 미리 보지 못한 구매" : `AI가 산 직전 ${s.rank}순위로 꼽음`}</small>
                    </span>
                  </li>
                ))}
                {salesSoFar.length === 0 && <li className="sim-muted">아직 판매가 없어요</li>}
              </ol>
            </div>
          </div>
        </div>

        <div className="sim-card">
          <h3>
            손님 {selected}의 관심 상품 <small>왼쪽에서 보고 있는 손님</small>
          </h3>
          {watching.length === 0 ? (
            <p className="sim-muted">{state.status === "waiting" ? "아직 들어오지 않았어요." : "쇼핑을 마치고 나갔어요."}</p>
          ) : (
            <ol className="sim-watch">
              {watching.slice(0, SHOWN_WATCHING).map((c) => {
                const reason = c.reasons.map(reasonSentence).find((r) => r && r.up);
                return (
                  <li key={c.item_id} className={c.decision === "구매 예상" ? "sim-watch-yes" : undefined}>
                    <img src={productFor(c.item_id).image} alt="" />
                    <span className="sim-watch-name">
                      {productName(c.item_id)}
                      <b>
                        {percent(c.probability, 0)} · {verdict(c.decision)}
                      </b>
                      <small>{reason ? `↑ ${reason.text}` : ""}</small>
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </section>
  );
}

function Kpi({ label, value, accent }) {
  return (
    <div className={accent ? "sim-kpi sim-kpi-accent" : "sim-kpi"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

// 알림은 한 줄만: 가장 위 알림 하나와 나머지 개수
function Alert({ alerts }) {
  if (alerts.length === 0) {
    return <div className="sim-alert sim-alert-ok">✓ 지금은 재고가 모자랄 상품이 없어요</div>;
  }
  const first = alerts[0];
  return (
    <div className={`sim-alert sim-alert-${first.status}`}>
      <img src={productFor(first.item).image} alt="" />
      <span>
        <b>{first.status === "soldout" ? "품절" : "⚠ 재고 부족 예상"}</b> {productName(first.item)}
        {first.status === "refill" ? ` · 남은 재고 ${first.stock}개, 10분 안에 팔릴 확률 ${percent(first.chance, 0)} → 채우세요` : " · 재고가 없어요"}
        {alerts.length > 1 && <em> 외 {alerts.length - 1}개</em>}
      </span>
    </div>
  );
}

// 10분 간격 예상(다음 10분)과 실제(그 10분 동안 AI가 보던 손님의 구매). 실제는 10분이 지나야 그린다.
function Chart({ store, t }) {
  const W = 300;
  const H = 150;
  const pad = { l: 18, r: 6, t: 6, b: 14 };
  const now = t / 60;
  const expected = [];
  const actual = [];
  for (let k = 0; k < store.minutes; k += 10) {
    if (k > now) break;
    expected.push([k, store.expected_next_10m[k]]);
    if (k + 10 <= now) actual.push([k, store.actual_known_next_10m[k]]);
  }
  const top = Math.max(4, ...store.actual_known_next_10m, ...store.expected_next_10m.map(Math.ceil));
  const x = (k) => pad.l + (k / store.minutes) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - v / top) * (H - pad.t - pad.b);
  const line = (points) => points.map(([k, v]) => `${x(k)},${y(v)}`).join(" ");
  return (
    <figure className="sim-chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="10분마다 예상 판매와 실제 판매">
        {[0, top].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} className="sim-grid" />
            <text x={pad.l - 4} y={y(v) + 3} className="sim-axis" textAnchor="end">
              {v}
            </text>
          </g>
        ))}
        <line x1={x(now)} x2={x(now)} y1={pad.t} y2={H - pad.b} className="sim-now" />
        {expected.length > 1 && <polyline points={line(expected)} className="sim-line-expected" />}
        {actual.length > 1 && <polyline points={line(actual)} className="sim-line-actual" />}
      </svg>
      <figcaption>
        <span><i className="sim-key-expected" />AI 예상</span>
        <span><i className="sim-key-actual" />실제 (10분 뒤 표시)</span>
      </figcaption>
    </figure>
  );
}
