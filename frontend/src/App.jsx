import { Routes, Route, Link, useLocation } from "react-router-dom";
import { ShoppingProvider } from "./context/ShoppingContext";
import StartPage from "./pages/StartPage";
import HomePage from "./pages/HomePage";
import ProductDetailPage from "./pages/ProductDetailPage";
import CheckoutPage from "./pages/CheckoutPage";
import WaitingPage from "./pages/WaitingPage";
import ResultPage from "./pages/ResultPage";
import "./styles.css";

function Layout() {
  const location = useLocation();
  const hideNavbar = location.pathname === "/"; // 체험시작 화면에는 상단바를 안 보여줌

  return (
    <>
      {!hideNavbar && (
        <nav className="navbar">
          <Link to="/main" className="brand">
            PickCast
          </Link>
        </nav>
      )}
      <Routes>
        <Route path="/" element={<StartPage />} />
        <Route path="/main" element={<HomePage />} />
        <Route path="/products/:id" element={<ProductDetailPage />} />
        <Route path="/checkout/:id" element={<CheckoutPage />} />
        <Route path="/waiting" element={<WaitingPage />} />
        <Route path="/result" element={<ResultPage />} />
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
