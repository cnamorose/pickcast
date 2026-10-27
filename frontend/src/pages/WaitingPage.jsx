import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useShopping } from "../context/ShoppingContext";
import { fetchSessionPrediction } from "../api/session";

// 결제 직후 보여주는 "결과대기" 화면.
// 여기서 실제로 백엔드 예측 API를 호출하고, 끝나면 결과 화면으로 자동 이동한다.
export default function WaitingPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { sessionId } = useShopping();
  const purchasedItem = location.state?.purchasedItem;

  useEffect(() => {
    // 결제페이지를 거치지 않고 바로 들어왔거나, 세션이 없는 경우 처리
    // (조회 기록은 서버에 있으므로 새로고침해도 세션만 있으면 결과를 받을 수 있다)
    if (!purchasedItem || !sessionId) {
      navigate("/main", { replace: true });
      return;
    }

    let cancelled = false;

    async function run() {
      try {
        const data = await fetchSessionPrediction(sessionId);
        if (!cancelled) {
          navigate("/result", {
            replace: true,
            state: { result: data, purchasedItem },
          });
        }
      } catch (err) {
        if (!cancelled) {
          navigate("/result", {
            replace: true,
            state: { error: err.message || "예측 처리 중 오류가 발생했어요.", purchasedItem },
          });
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page waiting-page">
      <h2>결과를 준비하고 있어요...</h2>
      <div className="spinner" />
    </div>
  );
}
