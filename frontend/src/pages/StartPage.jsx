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
      <span className="start-eyebrow">AI 구매 예측 체험</span>
      <h1>PickCast</h1>
      <p className="start-desc">
        평소처럼 쇼핑하고 마음에 드는 상품 하나를 결제해보세요.
        <br />
        AI가 둘러본 기록만으로 무엇을 살지 예측했는지 알려드려요.
      </p>
      <ol className="start-steps">
        <li>
          <b>1</b>상품 둘러보기
        </li>
        <li>
          <b>2</b>하나 골라 결제
        </li>
        <li>
          <b>3</b>AI 예측 확인
        </li>
      </ol>
      <div className="start-actions">
        <button className="btn btn-white" onClick={handleStart}>
          시작하기
        </button>
        {/* 실제 쇼핑 기록으로 산 상품을 맞히는 게임(사람 vs AI). 세션을 만들지 않는다. */}
        <button className="btn btn-outline-white" onClick={() => navigate("/guess")}>
          AI와 대결
        </button>
        {/* 쇼핑 체험과 별개인 시뮬레이션 화면. 세션을 만들지 않는다. */}
        <button className="btn btn-outline-white" onClick={() => navigate("/peak")}>
          피크타임 시뮬레이션
        </button>
        {/* 판매자(운영자)용 화면. 세션을 만들지 않는다. */}
        <button className="btn btn-outline-white" onClick={() => navigate("/admin")}>
          판매자 대시보드
        </button>
      </div>
    </div>
  );
}
