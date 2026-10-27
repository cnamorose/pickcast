import { useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { getProduct, getRelated, CATEGORY_LABELS } from "../data/products";
import { useShopping } from "../context/ShoppingContext";
import ProductCard from "../components/ProductCard";
import { formatPrice } from "../utils/format";

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

  // 다른 상품으로 이동하면 화면 맨 위부터 보여준다.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);

  if (!product) {
    return (
      <div className="page">
        <p>상품을 찾을 수 없어요.</p>
        <Link to="/main">메인으로</Link>
      </div>
    );
  }

  const categoryLabel = CATEGORY_LABELS[product.category];

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/main">홈</Link>
        <span>/</span>
        <Link to={`/main?cat=${product.category}`}>{categoryLabel}</Link>
        <span>/</span>
        <span>{product.name}</span>
      </div>

      <div className="detail">
        <div className="detail-image-wrap">
          <img src={product.image} alt={product.name} className="detail-image" />
        </div>

        <div className="detail-info">
          <div className="detail-category">{categoryLabel}</div>
          <h1 className="detail-title">{product.name}</h1>
          <div className="detail-price">{formatPrice(product.price)}</div>

          <p className="description">{product.description}</p>

          <dl className="info-table">
            <div>
              <dt>상품 정보</dt>
              <dd>{product.meta}</dd>
            </div>
            <div>
              <dt>배송</dt>
              <dd>무료배송 · 1~2일 이내 출고</dd>
            </div>
            <div>
              <dt>교환/반품</dt>
              <dd>수령 후 7일 이내 가능</dd>
            </div>
          </dl>

          <button className="btn btn-black btn-block" onClick={() => navigate(`/checkout/${product.id}`)}>
            구매하기
          </button>
        </div>
      </div>

      {related.length > 0 && (
        <section className="related">
          <h3 className="section-title">같은 카테고리 상품</h3>
          <div className="grid">
            {related.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
