import { Link } from "react-router-dom";
import { PRODUCTS, CATEGORIES } from "../data/products";

function formatPrice(price) {
  return `₩${price.toLocaleString("ko-KR")}`;
}

function ProductCard({ product }) {
  return (
    <div className="card">
      <Link to={`/products/${product.id}`}>
        <img src={product.image} alt={product.name} className="card-image" />
      </Link>
      <div className="card-title">{product.name}</div>
      <div className="card-price">{formatPrice(product.price)}</div>
      <Link to={`/products/${product.id}`} className="btn btn-black">
        상세보기
      </Link>
    </div>
  );
}

export default function HomePage() {
  return (
    <div>
      <div className="hero">
        <h1>PickCast</h1>
        <p>AI 이용한 구매 예측 사이트</p>
      </div>

      {CATEGORIES.map((category) => (
        <section key={category} className="section">
          <h2 className="category-title">{category}</h2>
          <div className="grid">
            {PRODUCTS.filter((p) => p.category === category).map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        </section>
      ))}

      <footer className="footer">
        <div>PickCast</div>
        <p className="attribution">
          데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)
        </p>
      </footer>
    </div>
  );
}

export { formatPrice };
