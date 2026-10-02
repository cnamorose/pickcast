import { useNavigate } from "react-router-dom";

// 사이트 진입 시 처음 보여주는 "체험시작" 화면.
// "시작하기"를 누르면 메인페이지(상품 목록)로 이동한다.
export default function StartPage() {
  const navigate = useNavigate();

  return (
    <div className="start-page">
      <h1>PickCast</h1>
      <button className="btn btn-black" onClick={() => navigate("/main")}>
        시작하기
      </button>
    </div>
  );
}
