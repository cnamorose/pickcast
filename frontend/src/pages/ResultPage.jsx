import { useLocation, Link } from "react-router-dom";

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

  const { candidates } = result.prediction;
  const featureLabels = result.feature_labels || {};
  const topCandidate = candidates[0];
  const matched = topCandidate && topCandidate.item_id === purchasedItem;
  const purchasedCandidate = candidates.find((c) => c.item_id === purchasedItem);

  // 상품을 하나만 보고 결제한 경우 후보가 그 상품 하나뿐이라 항상 1순위가 된다.
  // 이때는 "예측 성공" 메시지를 보여주지 않고 안내만 보여준다.
  const onlyOneViewed =
    purchasedCandidate && purchasedCandidate.features?.distinct_items_viewed === 1;

  const f = purchasedCandidate?.features || {};
  const { up, down } = splitFactors(purchasedCandidate?.shap?.contributions);
  const label = (key) => featureLabels[key] || key;

  return (
    <div className="page">
      <h2>구매한 상품: {purchasedItem}</h2>

      <div className="ranking">
        {candidates.map((c) => (
          <div
            className={`rank-row ${c.item_id === purchasedItem ? "rank-row-picked" : ""}`}
            key={c.item_id}
          >
            <span className={`rank-badge ${c.rank === 1 ? "rank-badge-first" : ""}`}>{c.rank}</span>
            <span className={c.rank === 1 ? "rank-name-first" : "rank-name"}>{c.item_id}</span>
            {c.item_id === purchasedItem && <span className="rank-picked-label">내가 고른 상품</span>}
          </div>
        ))}
      </div>

      {onlyOneViewed ? (
        <p className="info-note">
          상품을 하나만 보고 결제해서 AI가 비교할 후보가 없었어요. 여러 상품을 둘러볼수록 상품별
          예측이 더 뚜렷하게 갈려요.
        </p>
      ) : (
        <p className="predict-message">
          {matched ? "AI가 정확하게 예측했습니다!" : "AI 예측과 다른 상품을 선택했어요."}
        </p>
      )}

      <div className="explain-box">
        <div className="explain-title">예측 이유 ({purchasedItem})</div>

        {up.length === 0 && down.length === 0 ? (
          <p className="predict-message">이 상품에 대한 예측 이유 정보가 없어요.</p>
        ) : (
          <>
            {up.length > 0 && (
              <div className="factor-group">
                <div className="factor-heading factor-up">구매 가능성을 높인 요인</div>
                <ul className="explain-list">
                  {up.map(([key]) => (
                    <li key={key}>
                      {label(key)}: {formatFeatureValue(key, f[key])}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {down.length > 0 && (
              <div className="factor-group">
                <div className="factor-heading factor-down">구매 가능성을 낮춘 요인</div>
                <ul className="explain-list">
                  {down.map(([key]) => (
                    <li key={key}>
                      {label(key)}: {formatFeatureValue(key, f[key])}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        <p className="attribution">
          데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)
        </p>
      </div>

      <Link to="/" className="btn btn-black" style={{ marginTop: 24, display: "inline-block" }}>
        처음으로 (다음 체험)
      </Link>
    </div>
  );
}
