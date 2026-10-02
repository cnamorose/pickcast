// 상품 데이터 (데모용). 실제 이미지는 피그마에서 내보낸 파일로 나중에 교체하면 됨.
// id는 그대로 모델 호출 시 item_id로 사용됨 (모델은 이 값 자체를 피처로 쓰지 않으므로
// 실제 데이터셋 상품 ID와 매칭시키지 않아도 됨).
export const PRODUCTS = [
  {
    id: "TOP-01",
    category: "TOP",
    name: "TOP-01",
    price: 29000,
    image: "https://picsum.photos/seed/top01/600/600",
    description: "부드러운 코튼 소재의 베이직 티셔츠. 편안한 핏으로 데일리룩에 활용하기 좋습니다.",
    meta: "소재: 면 100% · 사이즈: Free",
  },
  {
    id: "TOP-02",
    category: "TOP",
    name: "TOP-02",
    price: 19000,
    image: "https://picsum.photos/seed/top02/600/600",
    description: "가벼운 니트 소재 반팔. 다양한 색상으로 매치하기 좋은 기본 아이템입니다.",
    meta: "소재: 면 혼방 · 사이즈: Free",
  },
  {
    id: "OUTER-01",
    category: "OUTER",
    name: "OUTER-01",
    price: 59000,
    image: "https://picsum.photos/seed/outer01/600/600",
    description: "빈티지한 워싱의 데님 자켓. 가볍게 걸치기 좋은 아우터입니다.",
    meta: "소재: 데님 100% · 사이즈: Free",
  },
  {
    id: "OUTER-02",
    category: "OUTER",
    name: "OUTER-02",
    price: 49000,
    image: "https://picsum.photos/seed/outer02/600/600",
    description: "미니멀한 디자인의 롱 코트. 깔끔한 실루엣이 특징입니다.",
    meta: "소재: 폴리 혼방 · 사이즈: Free",
  },
  {
    id: "SHOES-01",
    category: "SHOES",
    name: "SHOES-01",
    price: 99000,
    image: "https://picsum.photos/seed/shoes01/600/600",
    description: "포인트 컬러가 돋보이는 캐주얼 스니커즈.",
    meta: "소재: 캔버스 · 사이즈: 표준",
  },
  {
    id: "SHOES-02",
    category: "SHOES",
    name: "SHOES-02",
    price: 79000,
    image: "https://picsum.photos/seed/shoes02/600/600",
    description: "블랙&화이트 배색의 클래식 스니커즈.",
    meta: "소재: 가죽 · 사이즈: 표준",
  },
];

export const CATEGORIES = ["TOP", "OUTER", "SHOES"];

export function getProduct(id) {
  return PRODUCTS.find((p) => p.id === id);
}

export function getRelated(id) {
  return PRODUCTS.filter((p) => p.id !== id);
}
