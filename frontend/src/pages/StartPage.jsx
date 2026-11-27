import { useNavigate } from "react-router-dom";

// 사이트 진입 시 처음 보여주는 시작 화면 (판매자를 위한 AI 구매 예측).
// 왼쪽: 사이트 소개 / 오른쪽: 메뉴 카드 4개 (모델 성능, 판매 시뮬레이션, 판매자의 하루, 피크타임 우선 처리).
// 아직 만들지 않은 화면은 ready: false로 두어 "준비 중"으로 보여주고 누를 수 없게 한다.
const CARDS = [
  {
    key: "model",
    icon: "📊",
    tone: "ink",
    title: "모델 성능",
    desc: "과거 기록으로 공부한 AI가 처음 보는 미래 기간에서 얼마나 맞혔는지, 어떤 정보가 예측에 중요했는지 쉽게 보여줘요.",
    cta: "보기",
    path: "/model",
    ready: false,
  },
  {
    key: "simulation",
    icon: "🛍",
    tone: "accent",
    title: "판매 시뮬레이션",
    desc: "실제 쇼핑몰의 붐비는 두 시간을 다시 재생해요. 손님이 쇼핑하는 화면과, 같은 순간 판매자가 보는 화면을 나란히 볼 수 있어요.",
    steps: ["손님 화면", "판매자 화면", "AI가 맞혔는지"],
    cta: "보기",
    path: "/simulation",
    ready: true,
  },
  {
    key: "game",
    icon: "🎮",
    tone: "green",
    title: "판매자의 하루",
    desc: "쌓이는 주문을 처리하며 재고를 채우는 게임이에요. 대시보드의 AI 예측을 보고 미리 채워야 품절을 막을 수 있어요.",
    cta: "플레이",
    path: "/game",
    ready: false,
  },
  {
    key: "peak",
    icon: "⚡",
    tone: "warn",
    title: "피크타임 우선 처리",
    desc: "접속이 몰려 서버가 밀릴 때, 살 가능성이 높은 손님부터 처리하면 선착순보다 구매 손님을 더 지킬 수 있는지 실제 기록으로 재생해요.",
    note: "조회 기록만 쓰는 이전 모델(v2) 기준 결과예요",
    cta: "보기",
    path: "/peak",
    ready: true,
  },
];

export default function StartPage() {
  const navigate = useNavigate();

  return (
    <div className="start-page">
      {/* 소개는 위, 요점과 출처는 아래에 두어 세로를 고르게 쓴다 */}
      <section className="start-intro">
        <div className="start-intro-top">
          <span className="start-eyebrow">판매자를 위한 AI 구매 예측</span>
          <h1>PickCast</h1>
          <p className="start-lead">손님이 무엇을 살지 미리 알려주는 판매자 AI</p>
          <p className="start-desc">
            손님이 상품을 보고 장바구니에 담는 기록만으로 상품별 구매 가능성을 예측해요. 그리고 곧 팔릴 상품과 재고가 모자랄
            상품을 판매자에게 미리 알려줘요.
          </p>
        </div>
        <div className="start-intro-bottom">
          <ul className="start-points">
            <li>조회·장바구니 기록으로 상품별 구매 확률 예측 (학습에 쓰지 않은 미래 기간에서 단순 기준의 14.6배)</li>
            <li>앞으로 10분 예상 판매와 재고 알림</li>
            <li>개인 정보 없이 행동 기록만 사용</li>
          </ul>
          <p className="start-source">학습 데이터: Retailrocket recommender system dataset (CC BY-NC-SA 4.0)</p>
        </div>
      </section>

      <section className="start-menu" aria-label="메뉴 선택">
        {CARDS.map((card) => (
          <button
            key={card.key}
            className={`start-card start-card-${card.tone}${card.ready ? "" : " start-card-soon"}`}
            onClick={() => card.ready && navigate(card.path)}
            disabled={!card.ready}
          >
            <span className="start-card-icon" aria-hidden="true">
              {card.icon}
            </span>
            <h2>{card.title}</h2>
            <p>{card.desc}</p>
            {card.note && <small className="start-card-note">{card.note}</small>}
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
            <span className="start-card-cta">{card.ready ? `${card.cta} →` : "준비 중"}</span>
          </button>
        ))}
      </section>
    </div>
  );
}
