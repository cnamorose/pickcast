import { useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getProduct, getRelated } from "../data/products";
import { useShopping } from "../context/ShoppingContext";
import { formatPrice } from "./HomePage";

export default function ProductDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { logView } = useShopping();

  const product = getProduct(id);
  const related = getRelated(id);

  // 이 페이지에 들어올 때마다(=상품을 조회할 때마다) 조회 로그를 하나 남긴다.
  // 장바구니/최종선택 정보가 아니라 "봤다"는 사실만 기록.
  useEffect(() => {
    if (product) logView(product.id);
  }, [product, logView]);

  if (!product) {
    return (
      <div className="page">
        <p>상품을 찾을 수 없어요.</p>
        <Link to="/main">메인으로</Link>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="detail">
        <img src={product.image} alt={product.name} className="detail-image" />
        <div className="detail-info">
          <div className="detail-category">{product.category}</div>
          <h2>{product.name}</h2>
          <div className="price">{formatPrice(product.price)}</div>
          <p className="description">{product.description}</p>
          <button className="btn btn-black" onClick={() => navigate(`/checkout/${product.id}`)}>
            구매하기
          </button>
          <p className="meta">{product.meta}</p>
        </div>
      </div>

      <section className="section">
        <h3 className="section-title">관련 상품</h3>
        <div className="grid">
          {related.map((p) => (
            <div className="card" key={p.id}>
              <Link to={`/products/${p.id}`}>
                <img src={p.image} alt={p.name} className="card-image" />
              </Link>
              <div className="card-title">{p.name}</div>
              <div className="card-sub">{p.description}</div>
              <div className="card-price">{formatPrice(p.price)}</div>
              <Link to={`/products/${p.id}`} className="btn btn-black">
                상세보기
              </Link>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
