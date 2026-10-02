# Frontend

React 기반 사용자 체험 화면.

## 실행 방법

```bash
cd frontend
npm install
cp .env.example .env   # 필요하면 VITE_API_BASE를 실제 백엔드 주소로 수정
npm run dev
```

브라우저에서 http://localhost:5173 접속. 백엔드 서버(`backend/`)가 8000번 포트에서
같이 떠 있어야 결제 후 AI 예측 결과까지 확인할 수 있음.

## 폴더 구조

```
src/
  data/products.js        상품 목록 (데모용 6개: TOP/OUTER/SHOES)
  context/ShoppingContext 조회 로그(views)·구매 상품 상태 관리
  api/predict.js          백엔드 /predictions 호출
  pages/
    HomePage              메인 (카테고리별 상품 목록)
    ProductDetailPage     상품 상세 (진입 시 조회 이벤트 기록)
    CheckoutPage          결제 (결제 버튼 누르면 예측 API 호출)
    ResultPage            AI 결과 (순위 비교 + 예측 이유)
```

## 흐름

1. 메인에서 상품 클릭 → 상세페이지 진입 (조회 로그 기록)
2. 상세페이지에서 "구매하기" → 결제페이지
3. 결제페이지에서 "결제" → 그동안의 조회 로그로 예측 API 호출 → AI결과페이지로 이동
4. AI결과페이지에서 예측 순위와 실제 구매 상품 비교

## 상품 이미지 교체

지금은 picsum.photos 임시 이미지를 쓰고 있음. 피그마에서 내보낸 실제 이미지로 바꾸려면
`src/assets/`에 이미지 파일을 넣고 `src/data/products.js`의 `image` 값을 그 경로로 바꾸면 됨.
