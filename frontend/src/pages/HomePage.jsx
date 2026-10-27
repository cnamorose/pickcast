import { useSearchParams } from "react-router-dom";
import { PRODUCTS, CATEGORIES, CATEGORY_LABELS } from "../data/products";
import ProductCard from "../components/ProductCard";
import { formatPrice } from "../utils/format";

// 다른 파일에서 기존처럼 HomePage에서 가져다 써도 되도록 다시 내보낸다.
export { formatPrice };

export default function HomePage() {
  // 선택한 카테고리를 주소(?cat=TOP)에 남겨서, 상세 페이지에서 뒤로 가도 탭이 유지되게 한다.
  const [searchParams, setSearchParams] = useSearchParams();
  const selected = CATEGORIES.includes(searchParams.get("cat")) ? searchParams.get("cat") : "ALL";
  const shown = selected === "ALL" ? CATEGORIES : [selected];

  function selectTab(cat) {
    setSearchParams(cat === "ALL" ? {} : { cat });
  }

  return (
    <div>
      <section className="hero">
        <div className="hero-inner">
          <span className="hero-badge">2026 F/W COLLECTION</span>
          <h1>이번 시즌, 나에게 맞는 한 벌</h1>
          <p>상의부터 가방까지 48개 아이템을 둘러보세요.</p>
        </div>
      </section>

      <nav className="tabs" aria-label="카테고리">
        <div className="tabs-inner">
          {["ALL", ...CATEGORIES].map((cat) => (
            <button
              key={cat}
              className={`tab ${selected === cat ? "tab-active" : ""}`}
              onClick={() => selectTab(cat)}
            >
              {cat === "ALL" ? "전체" : CATEGORY_LABELS[cat]}
            </button>
          ))}
        </div>
      </nav>

      {shown.map((category) => (
        <section key={category} className="section">
          <div className="section-head">
            <h2 className="category-title">{CATEGORY_LABELS[category]}</h2>
            <span className="section-count">
              {PRODUCTS.filter((p) => p.category === category).length}개
            </span>
          </div>
          <div className="grid">
            {PRODUCTS.filter((p) => p.category === category).map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        </section>
      ))}

      <footer className="footer">
        <div className="footer-brand">PickCast</div>
        <p>졸업작품 데모 쇼핑몰입니다. 실제 결제는 이루어지지 않습니다.</p>
        <p className="attribution">
          데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)
        </p>
      </footer>
    </div>
  );
}
