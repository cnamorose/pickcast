import { useLocation, Link } from "react-router-dom";

function formatSeconds(sec) {
  if (sec == null) return "-";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `${m}분 ${s}초` : `${s}초`;
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
        <Link to="/main">메인으로</Link>
      </div>
    );
  }

  if (!result || !purchasedItem) {
    return (
      <div className="page">
        <p>결과 정보가 없어요. 상품을 구매한 뒤 다시 확인해주세요.</p>
        <Link to="/main">메인으로</Link>
      </div>
    );
  }

  const { candidates } = result.prediction;
  const featureLabels = result.feature_labels || {};
  const topCandidate = candidates[0];
  const matched = topCandidate && topCandidate.item_id === purchasedItem;
  const purchasedCandidate = candidates.find((c) => c.item_id === purchasedItem);

  // 상품을 하나만 보고 결제한 경우, 모든 확률이 동일하게 나온다 (가이드 문서 기준).
  const onlyOneViewed =
    purchasedCandidate && purchasedCandidate.features?.distinct_items_viewed === 1;

  const f = purchasedCandidate?.features || {};

  return (
    <div className="page">
      <h2>구매한 상품: {purchasedItem}</h2>

      <div className="ranking">
        {candidates.map((c) => (
          <div className={`rank-row ${c.item_id === purchasedItem ? "rank-row-picked" : ""}`} key={c.item_id}>
            <span className={`rank-badge ${c.rank === 1 ? "rank-badge-first" : ""}`}>{c.rank}</span>
            <span className={c.rank === 1 ? "rank-name-first" : "rank-name"}>{c.item_id}</span>
          </div>
        ))}
      </div>

      <p className="predict-message">
        {matched ? "AI가 정확하게 예측했습니다!" : "AI 예측과 다른 상품을 선택했어요."}
      </p>

      {onlyOneViewed && (
        <p className="info-note">
          상품을 하나만 보고 결제해서 모든 상품의 확률이 동일하게 나왔어요. 여러 상품을 둘러볼수록
          예측이 더 뚜렷하게 갈려요.
        </p>
      )}

      <div className="explain-box">
        <div className="explain-title">예측 이유</div>
        <ul className="explain-list">
          <li>
            {featureLabels.view_count || "조회 횟수"}: {f.view_count ?? "-"}회
          </li>
          <li>
            {featureLabels.distinct_items_viewed || "조회한 상품 수"}: {f.distinct_items_viewed ?? "-"}개
          </li>
          <li>
            {featureLabels.seconds_since_last_view || "마지막 조회 후 경과 시간"}:{" "}
            {formatSeconds(f.seconds_since_last_view)}
          </li>
        </ul>
        <p className="attribution">
          데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)
        </p>
      </div>

      <Link to="/main" className="btn btn-black" style={{ marginTop: 24, display: "inline-block" }}>
        메인으로
      </Link>
    </div>
  );
}
