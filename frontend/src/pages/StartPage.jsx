import { useNavigate } from "react-router-dom";
import { useShopping } from "../context/ShoppingContext";

// 사이트 진입 시 처음 보여주는 "체험시작" 화면.
// "시작하기"를 누르면 이전 체험 기록을 지우고 메인페이지(상품 목록)로 이동한다.
export default function StartPage() {
  const navigate = useNavigate();
  const { reset } = useShopping();

  function handleStart() {
    reset(); // 이전 사람의 조회 기록·구매 상품을 비워서 새 체험으로 시작
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
