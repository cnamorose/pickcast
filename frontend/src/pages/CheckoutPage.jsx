import { useParams, useNavigate, Link } from "react-router-dom";
import { getProduct, CATEGORY_LABELS } from "../data/products";
import { useShopping } from "../context/ShoppingContext";
import { formatPrice } from "../utils/format";

export default function CheckoutPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { purchase } = useShopping();

  const product = getProduct(id);

  if (!product) {
    return (
      <div className="page">
        <p>상품을 찾을 수 없어요.</p>
        <Link to="/main">메인으로</Link>
      </div>
    );
  }

  async function handlePay() {
    // 결제를 서버에 저장한 뒤 "결과대기" 화면으로 이동한다.
    // 실제 예측 API 호출은 결과대기 화면(WaitingPage)에서 처리한다.
    try {
      await purchase(product.id);
    } catch (err) {
      // 이미 결제한 세션(뒤로가기 후 재결제 등)이면 서버가 거절한다. 결과 화면은 그대로 보여준다.
      console.warn("결제 기록 저장 실패:", err);
    }
    navigate("/waiting", { state: { purchasedItem: product.id } });
  }

  return (
    <div className="page page-narrow">
      <h2 className="page-title">주문/결제</h2>

      <div className="checkout-box">
        <div className="checkout-label">주문 상품</div>
        <div className="checkout-item">
          <img src={product.image} alt={product.name} className="checkout-image" />
          <div>
            <div className="card-category">{CATEGORY_LABELS[product.category]}</div>
            <div className="checkout-title">{product.name}</div>
            <div className="checkout-sub">수량 1개</div>
          </div>
          <div className="checkout-price">{formatPrice(product.price)}</div>
        </div>
      </div>

      <div className="checkout-box">
        <div className="summary-row">
          <span>상품 금액</span>
          <span>{formatPrice(product.price)}</span>
        </div>
        <div className="summary-row">
          <span>배송비</span>
          <span>무료</span>
        </div>
        <div className="summary-row summary-total">
          <span>총 결제 금액</span>
          <span>{formatPrice(product.price)}</span>
        </div>
      </div>

      <p className="checkout-note">데모용 가상 결제로, 실제 결제는 이루어지지 않습니다.</p>

      <button className="btn btn-black btn-block" onClick={handlePay}>
        {formatPrice(product.price)} 결제하기
      </button>
    </div>
  );
}
