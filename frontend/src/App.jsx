import { Routes, Route, Link, useLocation } from "react-router-dom";
import { ShoppingProvider } from "./context/ShoppingContext";
import StartPage from "./pages/StartPage";
import HomePage from "./pages/HomePage";
import ProductDetailPage from "./pages/ProductDetailPage";
import CheckoutPage from "./pages/CheckoutPage";
import WaitingPage from "./pages/WaitingPage";
import ResultPage from "./pages/ResultPage";
import PeakPage from "./peak/PeakPage";
import "./styles.css";

function Layout() {
  const location = useLocation();
  const { pathname } = location;
  // 체험시작 화면과 피크타임 시뮬레이션 화면에는 쇼핑몰 상단바를 안 보여줌
  const hideNavbar = pathname === "/" || pathname === "/peak";
  // 상품 목록 버튼은 쇼핑 중(상세·결제)에만 보여준다.
  // 결제 후에는 결과 화면의 "처음으로"로만 나가야 새 세션으로 시작된다.
  const showListButton = pathname.startsWith("/products/") || pathname.startsWith("/checkout/");

  return (
    <>
      {!hideNavbar && (
        <nav className="navbar">
          {/* 로고는 링크가 아님: 결제 후 로고로 쇼핑에 돌아가면 끝난 세션에 조회가 쌓이지 않음 */}
          <span className="brand">PickCast</span>
          {showListButton && (
            <Link to="/main" className="nav-link">
              상품 목록
            </Link>
          )}
        </nav>
      )}
      <Routes>
        <Route path="/" element={<StartPage />} />
        <Route path="/main" element={<HomePage />} />
        <Route path="/products/:id" element={<ProductDetailPage />} />
        <Route path="/checkout/:id" element={<CheckoutPage />} />
        <Route path="/waiting" element={<WaitingPage />} />
        <Route path="/result" element={<ResultPage />} />
        <Route path="/peak" element={<PeakPage />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <ShoppingProvider>
      <Layout />
    </ShoppingProvider>
  );
}
