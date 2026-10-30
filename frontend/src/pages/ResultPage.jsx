import { useLocation, Link } from "react-router-dom";
import { getProduct, CATEGORY_LABELS } from "../data/products";
import { formatPrice } from "../utils/format";

// 피처 값을 사람이 읽기 쉬운 문장으로 바꾼다.
function formatSeconds(sec) {
  if (sec == null) return "-";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `${m}분 ${s}초` : `${s}초`;
}

function formatFeatureValue(key, value) {
  if (value == null) return "-";
  switch (key) {
    case "view_count":
    case "revisit_count":
    case "user_total_views":
      return `${value}회`;
    case "distinct_items_viewed":
      return `${value}개`;
    case "view_share":
      return `${Math.round(value * 100)}%`;
    case "seconds_since_first_view":
      return formatSeconds(value);
    case "seconds_since_last_view":
      // 0초 = 예측 시점(마지막 조회)에 이 상품을 보고 있었다는 뜻
      return value === 0 ? "0초 (방금 본 상품)" : formatSeconds(value);
    case "is_last_viewed":
      return value >= 1 ? "예" : "아니오";
    default:
      return String(value);
  }
}

// SHAP 기여도에서 확률을 올린 요인 / 내린 요인을 크기순으로 뽑는다.
// 기여도 숫자는 보정 전 점수 기준이라 퍼센트로 표시하지 않고, 방향과 순서만 쓴다.
function splitFactors(contributions, limit = 3) {
  const entries = Object.entries(contributions || {}).filter(([, v]) => v !== 0);
  const up = entries
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
  const down = entries
    .filter(([, v]) => v < 0)
    .sort((a, b) => a[1] - b[1])
    .slice(0, limit);
  return { up, down };
}

// 순위 목록은 상위 5개만 보여주고, 내가 고른 상품이 그 밖이면 맨 아래에 따로 붙인다.
const TOP_N = 5;

function percent(p) {
  if (p == null) return "-";
  const v = p * 100;
  return v < 0.1 ? "<0.1%" : `${v.toFixed(1)}%`;
}

// 내가 고른 상품 카드 (결과 화면 맨 위)
function PickedCard({ itemId, children }) {
  const p = getProduct(itemId);
  return (
    <section className="result-hero">
      {p && <img src={p.image} alt={itemId} className="result-hero-image" />}
      <div className="result-hero-info">
        <span className="result-hero-label">내가 고른 상품</span>
        <h1 className="result-hero-name">{itemId}</h1>
        {p && (
          <div className="result-hero-sub">
            {CATEGORY_LABELS[p.category]} · {p.type} · {p.color} · {formatPrice(p.price)}
          </div>
        )}
        {children}
      </div>
    </section>
  );
}

export default function ResultPage() {
  const location = useLocation();
  const { result, purchasedItem, error } = location.state || {};

  if (error) {
    return (
      <div className="page">
        <p className="error-text">
          {error} — 백엔드 서버가 켜져 있는지 확인해주세요 (VITE_API_BASE 설정 확인).
        </p>
        <Link to="/">처음으로</Link>
      </div>
    );
  }

  if (!result || !purchasedItem) {
    return (
      <div className="page">
        <p>결과 정보가 없어요. 상품을 구매한 뒤 다시 확인해주세요.</p>
        <Link to="/">처음으로</Link>
      </div>
    );
  }

  // 예측은 결제하러 들어간 마지막 방문 직전 기준이다 (백엔드에서 그 조회를 빼고 계산).
  // 구매한 상품만 보고 결제했으면 뺀 뒤 남는 조회가 없어 prediction이 null이다.
  if (!result.prediction) {
    return (
      <div className="page page-result">
        <PickedCard itemId={purchasedItem} />
        <p className="info-note">
          구매한 상품만 보고 결제해서, 결정하기 전의 기록으로 AI가 예측할 수 없었어요. 여러 상품을
          둘러본 뒤 결제하면 AI가 미리 맞혀볼 수 있어요.
        </p>
        <Link to="/" className="btn btn-black" style={{ marginTop: 24, display: "inline-block" }}>
          처음으로 (다음 체험)
        </Link>
      </div>
    );
  }

  const { candidates } = result.prediction;
  const featureLabels = result.feature_labels || {};
  const topCandidate = candidates[0];
  const matched = topCandidate && topCandidate.item_id === purchasedItem;
  const purchasedCandidate = candidates.find((c) => c.item_id === purchasedItem);

  // 결정하기 전에는 구매 상품을 보지 않아 AI 후보에 없었던 경우
  const notInCandidates = !purchasedCandidate;

  // 성공/실패 대신 구매 상품을 몇 순위로 예측했는지 보여준다 (모델 평가의 후보 순위와 같은 기준).
  // 결정 직전 기준이라 구매 상품 외에 다른 후보가 항상 있으므로 순위가 의미를 가진다.
  let resultMessage;
  if (notInCandidates) {
    resultMessage = "AI 후보에 없던 상품을 선택했어요.";
  } else if (matched) {
    resultMessage = "AI가 정확하게 예측했어요!";
  } else {
    resultMessage = `AI는 이 상품을 ${purchasedCandidate.rank}순위로 예측했어요 (후보 ${candidates.length}개 중).`;
  }

  const f = purchasedCandidate?.features || {};
  const { up, down } = splitFactors(purchasedCandidate?.shap?.contributions);
  const label = (key) => featureLabels[key] || key;

  // 순위순으로 정렬해서 상위 5개, 내가 고른 상품이 그 밖이면 따로 덧붙인다
  const ranked = [...candidates].sort((a, b) => a.rank - b.rank);
  const shown = ranked.slice(0, TOP_N);
  const pickedOutside = purchasedCandidate && purchasedCandidate.rank > TOP_N;
  const maxProb = Math.max(0.0001, ...ranked.map((c) => c.probability || 0));

  const verdictClass = notInCandidates ? "verdict-muted" : matched ? "verdict-hit" : "verdict-near";

  function RankRow({ c }) {
    const p = getProduct(c.item_id);
    const picked = c.item_id === purchasedItem;
    return (
      <li className={`result-rank-row ${picked ? "result-rank-picked" : ""}`}>
        <span className={`rank-badge ${c.rank === 1 ? "rank-badge-first" : ""}`}>{c.rank}</span>
        {p && <img src={p.image} alt={c.item_id} className="result-rank-thumb" />}
        <div className="result-rank-info">
          <b>
            {c.item_id}
            {picked && <span className="rank-picked-label">내가 고른 상품</span>}
          </b>
          <span>{p ? `${p.type} · ${p.color}` : ""}</span>
        </div>
        <div className="result-rank-prob">
          <div className="result-bar">
            <span style={{ width: `${((c.probability || 0) / maxProb) * 100}%` }} />
          </div>
          <b>{percent(c.probability)}</b>
        </div>
      </li>
    );
  }

  return (
    <div className="page page-result">
      <PickedCard itemId={purchasedItem}>
        <p className={`result-verdict ${verdictClass}`}>
          {matched ? "🎯 " : ""}
          {resultMessage}
        </p>
      </PickedCard>

      {result.excluded_views > 0 && (
        <p className="info-note">
          결제하러 들어간 마지막 상품 조회는 빼고, 그 직전까지의 기록으로 예측했어요.
        </p>
      )}

      <section className="result-section">
        <h3 className="section-title">AI가 예측한 구매 순위</h3>
        <p className="result-caption">둘러본 기록만으로 계산한 상품별 구매 확률이에요. (후보 {candidates.length}개)</p>
        <ol className="result-rank-list">
          {shown.map((c) => (
            <RankRow key={c.item_id} c={c} />
          ))}
          {pickedOutside && (
            <>
              <li className="result-rank-gap">···</li>
              <RankRow c={purchasedCandidate} />
            </>
          )}
        </ol>
      </section>

      <div className="explain-box">
        <div className="explain-title">예측 이유 ({purchasedItem})</div>

        {notInCandidates ? (
          <p className="predict-message">
            구매한 상품은 결정하기 전에 보지 않아서 AI 후보에 없었어요.
          </p>
        ) : up.length === 0 && down.length === 0 ? (
          <p className="predict-message">이 상품에 대한 예측 이유 정보가 없어요.</p>
        ) : (
          <div className="factor-columns">
            {up.length > 0 && (
              <div className="factor-group">
                <div className="factor-heading factor-up">▲ 구매 가능성을 높인 요인</div>
                <ul className="explain-list">
                  {up.map(([key]) => (
                    <li key={key}>
                      {label(key)}: <b>{formatFeatureValue(key, f[key])}</b>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {down.length > 0 && (
              <div className="factor-group">
                <div className="factor-heading factor-down">▼ 구매 가능성을 낮춘 요인</div>
                <ul className="explain-list">
                  {down.map(([key]) => (
                    <li key={key}>
                      {label(key)}: <b>{formatFeatureValue(key, f[key])}</b>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <p className="attribution">
          데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)
        </p>
      </div>

      <Link to="/" className="btn btn-black result-restart">
        처음으로 (다음 체험)
      </Link>
    </div>
  );
}
