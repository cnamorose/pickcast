import { useParams, useNavigate, Link } from "react-router-dom";
import { getProduct } from "../data/products";
import { useShopping } from "../context/ShoppingContext";
import { formatPrice } from "./HomePage";

export default function CheckoutPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { setPurchasedItem } = useShopping();

  const product = getProduct(id);

  if (!product) {
    return (
      <div className="page">
        <p>상품을 찾을 수 없어요.</p>
        <Link to="/main">메인으로</Link>
      </div>
    );
  }

  function handlePay() {
    // 결제 버튼을 누르면 바로 API를 부르지 않고, 먼저 "결과대기" 화면으로 이동한다.
    // 실제 예측 API 호출은 결과대기 화면(WaitingPage)에서 처리한다.
    setPurchasedItem(product.id);
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
