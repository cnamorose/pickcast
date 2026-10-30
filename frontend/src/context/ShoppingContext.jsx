import { createContext, useContext, useState, useCallback, useRef } from "react";
import { createSession, sendView, sendPurchase } from "../api/session";

// 체험 세션과 조회 기록을 들고 있는 컨텍스트.
// - sessionId: 서버 세션 번호. 새로고침해도 이어지도록 sessionStorage에도 저장
// - views: [{ timestamp, item_id }]  화면 표시용 사본. 원본은 서버 DB에 저장됨
//          (장바구니/최종선택 정보는 절대 넣지 않음)
// - purchasedItem: 결제 순간에만 정해짐
// - stage: 조회 API가 돌려준 구매 의도 단계 { stage, items } (사용자 맞춤 화면용)
// - stageModal: 지금 띄울 단계 모달. 단계가 바뀔 때만 열리고, 닫으면 같은 단계 동안 다시 안 열린다
// - wishlist, priceAlerts: 데모용 찜·가격 알림 목록 (화면 안에서만 쓰고 서버에 저장하지 않음)

const SESSION_KEY = "pickcast_session_id";

function loadSessionId() {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

function saveSessionId(id) {
  try {
    if (id) sessionStorage.setItem(SESSION_KEY, id);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // 저장소를 쓸 수 없어도 체험은 계속된다 (새로고침 시에만 세션이 끊김)
  }
}

const ShoppingContext = createContext(null);

export function ShoppingProvider({ children }) {
  const [sessionId, setSessionId] = useState(loadSessionId);
  const [views, setViews] = useState([]);
  const [purchasedItem, setPurchasedItem] = useState(null);
  const [stage, setStage] = useState(null);
  const [stageModal, setStageModal] = useState(null);
  const [wishlist, setWishlist] = useState([]);
  const [priceAlerts, setPriceAlerts] = useState([]);

  // 콜백 안에서 최신 값을 쓰기 위한 ref
  const sessionRef = useRef(sessionId);
  const sessionPromiseRef = useRef(null);
  const lastViewRef = useRef(null);
  // 조회 전송을 순서대로 이어 붙이는 체인. 결제 전에 남은 전송을 모두 기다린다.
  const pendingRef = useRef(Promise.resolve());
  // 마지막으로 받은 단계 이름. 단계가 바뀌었는지 비교할 때 쓴다.
  const lastStageRef = useRef(null);

  const applySession = useCallback((id) => {
    sessionRef.current = id;
    saveSessionId(id);
    setSessionId(id);
  }, []);

  // 세션이 없으면(시작 화면을 거치지 않고 들어온 경우) 그때 하나 만든다.
  const ensureSession = useCallback(async () => {
    if (sessionRef.current) return sessionRef.current;
    if (!sessionPromiseRef.current) {
      sessionPromiseRef.current = createSession(null)
        .then(({ session_id }) => {
          applySession(session_id);
          return session_id;
        })
        .finally(() => {
          sessionPromiseRef.current = null;
        });
    }
    return sessionPromiseRef.current;
  }, [applySession]);

  // "시작하기": 이전 기록을 비우고 새 세션을 만든다.
  // DB의 이전 기록은 지우지 않고, 결제 없이 끝났다면 서버가 abandoned로 닫는다.
  const startSession = useCallback(async () => {
    const previous = sessionRef.current;
    applySession(null);
    setViews([]);
    setPurchasedItem(null);
    setStage(null);
    setStageModal(null);
    setWishlist([]);
    setPriceAlerts([]);
    lastStageRef.current = null;
    lastViewRef.current = null;
    pendingRef.current = Promise.resolve();

    const { session_id } = await createSession(previous);
    applySession(session_id);
  }, [applySession]);

  // 조회 응답의 단계를 반영한다.
  // 단계가 바뀔 때만 모달을 연다: comparing(비교 모달), leaving(찜·가격 알림 모달).
  // decided는 모달 없이 상세 화면에서 구매 버튼을 강조하고, browsing은 아무것도 띄우지 않는다.
  // 같은 단계가 이어지면 상품 목록(items)만 갱신하고 모달은 다시 열지 않는다.
  const applyStage = useCallback((next) => {
    if (!next || !next.stage) return;
    const info = { stage: next.stage, items: next.items || [] };
    setStage(info);
    if (info.stage === lastStageRef.current) return;
    lastStageRef.current = info.stage;
    const needsModal = (info.stage === "comparing" && info.items.length >= 2) || (info.stage === "leaving" && info.items.length >= 1);
    setStageModal(needsModal ? info : null);
  }, []);

  // 상품 상세페이지를 볼 때마다 조회 이벤트를 하나 보낸다.
  // 개발 모드(React.StrictMode)에서는 useEffect가 두 번 실행되어 같은 조회가
  // 중복 기록되므로, 직전 기록과 같은 상품이 1초 안에 다시 들어오면 건너뛴다.
  const logView = useCallback(
    (itemId) => {
      const now = Date.now();
      const last = lastViewRef.current;
      if (last && last.item_id === itemId && now - last.timestamp < 1000) {
        return;
      }
      lastViewRef.current = { timestamp: now, item_id: itemId };
      setViews((prev) => [...prev, { timestamp: now, item_id: itemId }]);

      pendingRef.current = pendingRef.current
        .then(ensureSession)
        .then((id) => sendView(id, itemId))
        .then((res) => applyStage(res?.stage))
        .catch((err) => console.warn("조회 기록 전송 실패:", err));
    },
    [ensureSession, applyStage]
  );

  // 결제: 남은 조회 전송을 마친 뒤 결제를 저장한다.
  const purchase = useCallback(
    async (itemId) => {
      setPurchasedItem(itemId);
      await pendingRef.current;
      const id = await ensureSession();
      await sendPurchase(id, itemId);
    },
    [ensureSession]
  );

  const closeStageModal = useCallback(() => setStageModal(null), []);

  const toggleWishlist = useCallback((itemId) => {
    setWishlist((prev) => (prev.includes(itemId) ? prev.filter((x) => x !== itemId) : [...prev, itemId]));
  }, []);

  const togglePriceAlert = useCallback((itemId) => {
    setPriceAlerts((prev) => (prev.includes(itemId) ? prev.filter((x) => x !== itemId) : [...prev, itemId]));
  }, []);

  const value = {
    sessionId,
    views,
    purchasedItem,
    logView,
    purchase,
    startSession,
    stage,
    stageModal,
    closeStageModal,
    wishlist,
    toggleWishlist,
    priceAlerts,
    togglePriceAlert,
  };

  return <ShoppingContext.Provider value={value}>{children}</ShoppingContext.Provider>;
}

export function useShopping() {
  const ctx = useContext(ShoppingContext);
  if (!ctx) throw new Error("useShopping은 ShoppingProvider 안에서만 쓸 수 있어요.");
  return ctx;
}
