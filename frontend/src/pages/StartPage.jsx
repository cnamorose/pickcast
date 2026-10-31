import { useNavigate } from "react-router-dom";
import { useShopping } from "../context/ShoppingContext";

// 사이트 진입 시 처음 보여주는 "체험시작" 화면.
// 왼쪽(1): 사이트 소개 / 오른쪽(2): 체험 4가지 카드.
// "쇼핑 체험하기"만 새 세션을 만들고 메인페이지(상품 목록)로 이동한다. 나머지는 세션을 만들지 않는다.
const CARDS = [
  {
    key: "shop",
    icon: "🛍",
    tone: "accent",
    title: "쇼핑 체험하기",
    desc: "평소처럼 상품을 둘러보고 하나를 결제하면, AI가 둘러본 기록만으로 무엇을 살지 맞혔는지 알려드려요.",
    steps: ["상품 둘러보기", "하나 골라 결제", "AI 예측 확인"],
    cta: "시작하기",
  },
  {
    key: "guess",
    icon: "🤖",
    tone: "green",
    title: "AI와 대결",
    desc: "실제 쇼핑몰 고객의 조회 기록을 보고, 그 사람이 산 상품을 맞혀 보세요. AI와 3라운드 점수 대결이에요.",
    cta: "도전하기",
    path: "/guess",
  },
  {
    key: "peak",
    icon: "⚡",
    tone: "warn",
    title: "피크타임 시뮬레이션",
    desc: "접속이 몰려 서버가 밀릴 때, 살 가능성이 높은 손님부터 처리하면 무엇이 달라지는지 실제 기록으로 재생해요.",
    cta: "보기",
    path: "/peak",
  },
  {
    key: "admin",
    icon: "📊",
    tone: "ink",
    title: "판매자 대시보드",
    desc: "지금 쇼핑 중인 손님들의 구매 단계, 상품별 예상 판매량, 운영 인사이트를 한눈에 봐요.",
    cta: "보기",
    path: "/admin",
  },
];

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
      {/* 소개는 위, 요점과 출처는 아래에 두어 세로를 고르게 쓴다 */}
      <section className="start-intro">
        <div className="start-intro-top">
          <span className="start-eyebrow">AI 구매 예측 체험</span>
          <h1>PickCast</h1>
          <p className="start-lead">고객이 무엇을 살지 미리 읽는 쇼핑몰 AI</p>
          <p className="start-desc">
            상품을 몇 번, 어떤 순서로 봤는지 같은 조회 기록만으로 고객이 어떤 상품을 살지 예측해요. 그리고 그 예측을 쇼핑몰
            운영에 활용하는 서비스들을 만들었어요.
          </p>
        </div>
        <div className="start-intro-bottom">
          <ul className="start-points">
            <li>조회 기록만으로 상품별 구매 확률 예측</li>
            <li>예측을 활용한 맞춤 화면, 판매자 대시보드, 피크타임 우선 처리</li>
            <li>개인 정보 없이 행동 기록만 사용</li>
          </ul>
          <p className="start-source">학습 데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)</p>
        </div>
      </section>

      <section className="start-menu" aria-label="체험 선택">
        {CARDS.map((card) => (
          <button
            key={card.key}
            className={`start-card start-card-${card.tone}`}
            onClick={() => (card.path ? navigate(card.path) : handleStart())}
          >
            <span className="start-card-icon" aria-hidden="true">
              {card.icon}
            </span>
            <h2>{card.title}</h2>
            <p>{card.desc}</p>
            {card.steps && (
              <ol className="start-card-steps">
                {card.steps.map((step, i) => (
                  <li key={step}>
                    <b>{i + 1}</b>
                    {step}
                  </li>
                ))}
              </ol>
            )}
            <span className="start-card-cta">{card.cta} →</span>
          </button>
        ))}
      </section>
    </div>
  );
}
