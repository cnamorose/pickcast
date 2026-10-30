import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getProduct, CATEGORY_LABELS } from "../data/products";
import { useShopping } from "../context/ShoppingContext";
import { formatPrice } from "../utils/format";

// 구매 의도 단계별 모달 (사용자 맞춤 화면, 확장 기능 1).
// - comparing(고민 중): 고민 중인 상품 2~3개를 나란히 비교하는 모달
// - leaving(떠나려는 중): 관심이 멀어지는 상품을 찜하거나 가격 알림을 받게 하는 모달
// 단계가 바뀔 때만 열리고(ShoppingContext의 applyStage), 닫으면 같은 단계 동안 다시 열리지 않는다.

function CompareModal({ items, onClose }) {
  const navigate = useNavigate();
  const products = items.map(getProduct).filter(Boolean);
  if (products.length < 2) return null;
  const prices = products.map((p) => p.price);
  const minPrice = Math.min(...prices);
  // 가격이 모두 같으면 "가장 저렴" 표시를 붙이지 않는다. 가장 싼 상품이 하나일 때만 붙인다.
  const cheapestCount = prices.filter((x) => x === minPrice).length;

  function open(id) {
    onClose();
    navigate(`/products/${id}`);
  }

  return (
    <>
      <div className="stage-modal-head">
        <span className="stage-badge stage-badge-comparing">고민 중이신가요?</span>
        <h2 id="stage-modal-title">비슷한 상품을 한눈에 비교해보세요</h2>
        <p>최근에 번갈아 보신 상품 {products.length}개예요.</p>
      </div>

      <div className="compare-grid" style={{ gridTemplateColumns: `repeat(${products.length}, 1fr)` }}>
        {products.map((p) => (
          <div className="compare-col" key={p.id}>
            <div className="compare-image-wrap">
              <img src={p.image} alt={p.name} className="compare-image" />
            </div>
            <div className="compare-name">{p.name}</div>
            <div className="compare-price">
              {formatPrice(p.price)}
              {p.price === minPrice && cheapestCount === 1 && <span className="compare-tag">가장 저렴</span>}
            </div>
            <dl className="compare-rows">
              <div>
                <dt>종류</dt>
                <dd>
                  {CATEGORY_LABELS[p.category]} · {p.type}
                </dd>
              </div>
              <div>
                <dt>색상</dt>
                <dd>{p.color}</dd>
              </div>
              <div>
                <dt>정보</dt>
                <dd>{p.meta}</dd>
              </div>
            </dl>
            <button className="btn btn-black btn-block" onClick={() => open(p.id)}>
              이 상품 보기
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

function LeavingModal({ itemId, onClose }) {
  const navigate = useNavigate();
  const { wishlist, toggleWishlist, priceAlerts, togglePriceAlert } = useShopping();
  const product = getProduct(itemId);
  if (!product) return null;
  const saved = wishlist.includes(product.id);
  const alerted = priceAlerts.includes(product.id);

  return (
    <>
      <div className="stage-modal-head">
        <span className="stage-badge stage-badge-leaving">아직 결정하기 어려우신가요?</span>
        <h2 id="stage-modal-title">찜해두고 나중에 다시 보세요</h2>
        <p>가격이 내려가면 알려드릴게요.</p>
      </div>

      <div className="leaving-card">
        <img src={product.image} alt={product.name} className="leaving-image" />
        <div className="leaving-info">
          <div className="card-category">{CATEGORY_LABELS[product.category]}</div>
          <div className="leaving-name">{product.name}</div>
          <div className="leaving-price">{formatPrice(product.price)}</div>
          <p className="leaving-desc">{product.description}</p>
        </div>
      </div>

      <div className="leaving-actions">
        <button
          className={`btn btn-block ${saved ? "btn-black" : "btn-line"}`}
          onClick={() => toggleWishlist(product.id)}
        >
          {saved ? "♥ 찜했어요" : "♡ 찜하기"}
        </button>
        <button
          className={`btn btn-block ${alerted ? "btn-black" : "btn-line"}`}
          onClick={() => togglePriceAlert(product.id)}
        >
          {alerted ? "🔔 가격 알림 신청됨" : "🔔 가격 내리면 알림 받기"}
        </button>
      </div>
      {(saved || alerted) && (
        <p className="leaving-done">데모용 기능이라 실제 알림은 보내지 않아요.</p>
      )}
      <button
        className="stage-modal-link"
        onClick={() => {
          onClose();
          navigate(`/products/${product.id}`);
        }}
      >
        상품 다시 보기
      </button>
    </>
  );
}

export default function StageModal() {
  const { stageModal, closeStageModal } = useShopping();

  // ESC로 닫기
  useEffect(() => {
    if (!stageModal) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") closeStageModal();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stageModal, closeStageModal]);

  if (!stageModal) return null;

  const { stage, items } = stageModal;
  const wide = stage === "comparing" && items.length >= 3;

  return (
    <div className="stage-overlay" onClick={closeStageModal}>
      <div
        className={`stage-modal ${wide ? "stage-modal-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="stage-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="stage-modal-close" onClick={closeStageModal} aria-label="닫기">
          ×
        </button>
        {stage === "comparing" && <CompareModal items={items} onClose={closeStageModal} />}
        {stage === "leaving" && <LeavingModal itemId={items[0]} onClose={closeStageModal} />}
      </div>
    </div>
  );
}
