import { useParams, useNavigate, Link } from "react-router-dom";
import { getProduct } from "../data/products";
import { useShopping } from "../context/ShoppingContext";
import { formatPrice } from "./HomePage";

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
    <div className="page">
      <h2>총액: {formatPrice(product.price)}</h2>
      <div className="checkout-item">
        <img src={product.image} alt={product.name} className="checkout-image" />
        <div>
          <div className="checkout-title">
            {product.name} / 1 / {formatPrice(product.price)}
          </div>
          <p className="description">{product.description}</p>
        </div>
      </div>

      <button className="btn btn-black pay-btn" onClick={handlePay}>
        결제
      </button>
    </div>
  );
}
