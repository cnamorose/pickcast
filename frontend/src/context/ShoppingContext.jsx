import { createContext, useContext, useState, useCallback } from "react";

// 조회 로그(views)와 최종 구매 상품을 세션 동안 들고 있는 컨텍스트.
// - views: [{ timestamp, item_id }]  (장바구니/최종선택 정보는 절대 넣지 않음)
// - purchasedItem: 결제 순간에만 정해짐

const ShoppingContext = createContext(null);

export function ShoppingProvider({ children }) {
  const [views, setViews] = useState([]);
  const [purchasedItem, setPurchasedItem] = useState(null);

  // 상품 상세페이지를 볼 때마다 조회 이벤트를 하나 쌓는다.
  // 개발 모드(React.StrictMode)에서는 useEffect가 두 번 실행되어 같은 조회가
  // 중복 기록되므로, 직전 기록과 같은 상품이 1초 안에 다시 들어오면 건너뛴다.
  const logView = useCallback((itemId) => {
    setViews((prev) => {
      const now = Date.now();
      const last = prev[prev.length - 1];
      if (last && last.item_id === itemId && now - last.timestamp < 1000) {
        return prev;
      }
      return [...prev, { timestamp: now, item_id: itemId }];
    });
  }, []);

  const reset = useCallback(() => {
    setViews([]);
    setPurchasedItem(null);
  }, []);

  const value = { views, purchasedItem, setPurchasedItem, logView, reset };

  return <ShoppingContext.Provider value={value}>{children}</ShoppingContext.Provider>;
}

export function useShopping() {
  const ctx = useContext(ShoppingContext);
  if (!ctx) throw new Error("useShopping은 ShoppingProvider 안에서만 쓸 수 있어요.");
  return ctx;
}
