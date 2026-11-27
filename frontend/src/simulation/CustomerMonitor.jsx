import { formatPrice } from "../utils/format";
import {
  cartCount,
  categoryName,
  clockText,
  customerState,
  customerSubject,
  customerTopic,
  durationText,
  outcomeLines,
  productFor,
  productName,
} from "./simData";

// 왼쪽: 손님이 보는 컴퓨터 화면. 위 탭으로 손님을 고르고, 모니터 안 쇼핑몰에서
// 마우스 커서가 상품을 누르고·담고·결제하는 모습을 보여준다.

const STATUS = {
  waiting: { label: "아직 안 옴", className: "sim-dot-wait" },
  shopping: { label: "쇼핑 중", className: "sim-dot-live" },
  left: { label: "나감", className: "sim-dot-left" },
};

export default function CustomerMonitor({ journeys, selected, onSelect, auto, onToggleAuto, t, window, threshold }) {
  const journey = journeys.find((j) => j.id === selected);
  const state = customerState(journey, t);

  return (
    <section className="sim-customer" aria-label="손님이 보는 화면">
      <div className="sim-customer-head">
        <span className="sim-section-badge">👤 손님이 보는 화면</span>
        <button className={auto ? "sim-toggle sim-toggle-on" : "sim-toggle"} onClick={onToggleAuto}>
          {auto ? "● 움직이는 손님 자동으로 따라가는 중" : "○ 자동으로 따라가기"}
        </button>
      </div>

      <div className="sim-tabs" role="tablist" aria-label="손님 고르기">
        {journeys.map((j) => {
          const s = customerState(j, t);
          return (
            <button
              key={j.id}
              role="tab"
              aria-selected={j.id === selected}
              className={j.id === selected ? "sim-tab sim-tab-on" : "sim-tab"}
              onClick={() => onSelect(j.id)}
            >
              <span className={`sim-dot ${STATUS[s.status].className}`} />
              손님 {j.id}
              <small>{STATUS[s.status].label}</small>
            </button>
          );
        })}
      </div>

      <div className="sim-monitor">
        <div className="sim-screen">
          {state.status === "waiting" && <Waiting journey={journey} state={state} t={t} window={window} />}
          {state.status === "shopping" && <ShopPage journey={journey} index={state.index} />}
          {state.status === "left" && <Left journey={journey} threshold={threshold} />}
        </div>
        <div className="sim-monitor-chin" />
        <div className="sim-monitor-neck" />
        <div className="sim-monitor-foot" />
      </div>

      {state.status === "shopping" && <Dwell journey={journey} state={state} />}
      <Path journey={journey} index={state.status === "waiting" ? -1 : state.index} />
    </section>
  );
}

function ShopHeader({ count }) {
  return (
    <div className="sim-shop-head">
      <span className="sim-shop-logo">🛍 Pickcast Shop</span>
      <span className="sim-shop-search">찾고 싶은 옷을 검색해 보세요</span>
      <span className="sim-shop-cart" aria-label={`장바구니 ${count}개`}>
        🛒{count > 0 && <b>{count}</b>}
      </span>
    </div>
  );
}

function ShopPage({ journey, index }) {
  const step = journey.steps[index];
  const product = productFor(step.item_id);
  const paid = step.event === "transaction";
  return (
    <div className="sim-shop">
      <ShopHeader count={cartCount(journey, index)} />
      <div key={index} className="sim-shop-body">
        {paid ? (
          <div className="sim-paid">
            <img src={product.image} alt="" />
            <strong>🎉 결제 완료!</strong>
            <span>{productName(step.item_id)}</span>
          </div>
        ) : (
          <div className="sim-product">
            <div className="sim-product-photo">
              <img src={product.image} alt="" />
            </div>
            <div className="sim-product-info">
              <span className="sim-product-cat">{categoryName(step.item_id)}</span>
              <h3>{productName(step.item_id)}</h3>
              <p className="sim-product-price">{formatPrice(product.price)}</p>
              <span className={step.event === "addtocart" ? "sim-btn sim-btn-cart sim-btn-pressed" : "sim-btn sim-btn-cart"}>
                {step.event === "addtocart" ? "✓ 담았어요" : "장바구니 담기"}
              </span>
              <span className="sim-btn sim-btn-buy">바로 구매</span>
            </div>
          </div>
        )}
        <span className={`sim-cursor sim-cursor-${step.event}`} aria-hidden="true">
          <svg viewBox="0 0 24 24" width="26" height="26">
            <path d="M4 2 L4 20 L9 15 L12.5 22 L15.5 20.5 L12 14 L19 14 Z" fill="#fff" stroke="#15191e" strokeWidth="1.6" strokeLinejoin="round" />
          </svg>
          <i className="sim-click" />
        </span>
      </div>
    </div>
  );
}

function Waiting({ journey, state, t, window }) {
  return (
    <div className="sim-shop">
      <ShopHeader count={0} />
      <div className="sim-empty-screen">
        <span className="sim-empty-emoji">💤</span>
        <strong>{customerTopic(journey.id)} 아직 들어오지 않았어요</strong>
        <span>
          {clockText(window, t + state.enterIn)}에 들어와요 ({durationText(state.enterIn)} 뒤)
        </span>
      </div>
    </div>
  );
}

function Left({ journey, threshold }) {
  return (
    <div className="sim-shop">
      <ShopHeader count={0} />
      <div className="sim-empty-screen sim-left-screen">
        <span className="sim-empty-emoji">👋</span>
        <strong>{customerSubject(journey.id)} 쇼핑을 마치고 나갔어요</strong>
        <span className="sim-left-type">{journey.label}</span>
        {outcomeLines(journey, threshold).map((o, i) => (
          <div key={i} className={`sim-outcome sim-outcome-${o.tone}`}>
            <b>{o.title}</b>
            <span>{o.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Dwell({ journey, state }) {
  const step = journey.steps[state.index];
  return (
    <div className="sim-dwell">
      <span>
        {step.dwell_seconds == null ? "손님의 마지막 행동이에요" : `⏱ 이 화면에 ${durationText(step.dwell_seconds)} 머물러요`}
      </span>
      <span className="sim-dwell-bar">
        <i style={{ width: `${state.progress * 100}%` }} />
      </span>
    </div>
  );
}

function Path({ journey, index }) {
  if (index < 0) return null;
  return (
    <div className="sim-path">
      <span>{customerSubject(journey.id)} 지나온 길</span>
      <ol>
        {journey.steps.slice(0, index + 1).map((s, i) => (
          <li key={i} className={i === index ? "sim-path-now" : "sim-path-done"}>
            <img src={productFor(s.item_id).image} alt={productName(s.item_id)} />
            {s.event !== "view" && <small>{s.event === "addtocart" ? "🛒" : "💳"}</small>}
          </li>
        ))}
      </ol>
    </div>
  );
}
