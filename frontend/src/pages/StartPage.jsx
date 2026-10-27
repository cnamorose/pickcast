import { useNavigate } from "react-router-dom";
import { useShopping } from "../context/ShoppingContext";

// 사이트 진입 시 처음 보여주는 "체험시작" 화면.
// "시작하기"를 누르면 새 세션을 만들고 메인페이지(상품 목록)로 이동한다.
export default function StartPage() {
  const navigate = useNavigate();
  const { startSession } = useShopping();

  async function handleStart() {
    try {
      // 이전 사람의 조회 기록·구매 상품을 비우고 새 세션으로 시작
      await startSession();
    } catch (err) {
      // 서버가 꺼져 있어도 쇼핑은 시작한다. 첫 조회 때 세션 생성을 다시 시도한다.
      console.warn("세션 생성 실패:", err);
    }
    navigate("/main");
  }

  return (
    <div className="start-page">
      <h1>PickCast</h1>
      <button className="btn btn-black" onClick={handleStart}>
        시작하기
      </button>
    </div>
  );
}
