import { Link } from "react-router-dom";
import { CATEGORY_LABELS } from "../data/products";
import { formatPrice } from "../utils/format";

// 상품 카드. 카드 전체를 누르면 상세 페이지로 이동한다.
export default function ProductCard({ product }) {
  return (
    <Link to={`/products/${product.id}`} className="card">
      <div className="card-image-wrap">
        <img src={product.image} alt={product.name} className="card-image" loading="lazy" />
      </div>
      <div className="card-body">
        <div className="card-category">{CATEGORY_LABELS[product.category]}</div>
        <div className="card-title">{product.name}</div>
        <div className="card-price">{formatPrice(product.price)}</div>
      </div>
    </Link>
  );
}
