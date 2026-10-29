# Backend

FastAPI 기반 API 서버와 모델 추론 연동을 개발합니다.

## 주요 기능

* 체험 세션 관리
* 상품 정보 제공 및 조회 이벤트 수집
* 쇼핑 종료 시 모델 추론 실행
* 최종 상품 선택 전 예측 결과 확정 및 저장
* 가상 구매 결과 저장
* 가상 결제 완료 후 예측과 실제 선택 비교 결과 제공

## 개발 원칙

* 최종 선택 정보가 모델 입력에 포함되지 않도록 합니다.
* 학습과 서비스에서 동일한 피처 계산 규칙을 사용합니다.

## 개발 환경

* Python 3.13+
* FastAPI
* Uvicorn
* PostgreSQL 17 (Docker), SQLModel

## 실행 방법

프로젝트 루트(`pickcast`)에서 실행합니다.

### 1. 환경변수 파일 만들기

처음 한 번만 합니다. `.env`는 커밋하지 않습니다.

```powershell
Copy-Item .env.example .env
```

`.env`를 열어 `POSTGRES_PASSWORD`를 채우고, `DATABASE_URL`의 `<POSTGRES_PASSWORD>` 자리에도 같은 값을 넣습니다.

### 2. DB 실행

Docker Desktop을 켠 뒤 실행합니다. 데이터는 Docker 볼륨에 남아서 컨테이너를 내렸다 올려도 유지됩니다.

```powershell
docker compose up -d
```

* DB: `127.0.0.1:15432` (5432는 Windows 예약 포트 범위와 겹쳐서 15432를 씁니다.)
* 테이블(`sessions`, `views`, `purchases`)은 서버가 시작될 때 자동으로 만들어집니다.

### 3. 가상환경 활성화

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
backend\venv\Scripts\Activate.ps1
```

### 4. 패키지 설치

```powershell
pip install -r backend\requirements.txt
```

### 5. 서버 실행

```powershell
python -m uvicorn backend.app.main:app --reload
```

서버가 실행되면 다음 주소에서 확인할 수 있습니다.

* API 문서: `http://127.0.0.1:8000/docs`
* 상태 확인: `http://127.0.0.1:8000/health` → `"db": "connected"`가 나오면 DB 연결 정상

### 6. 테스트

DB나 서버 없이 실행됩니다.

```powershell
python -m unittest discover -s backend/tests -t . -v
```

## DB 확인

웹 화면(Adminer): `http://localhost:8080`

* 시스템: PostgreSQL
* 서버: `db`
* 사용자 / 비밀번호 / 데이터베이스: `.env`에 넣은 값

테스트 데이터를 모두 지우려면 볼륨째 삭제한 뒤 다시 실행합니다.

```powershell
docker compose down -v
docker compose up -d
```

## API

체험 한 번이 세션 하나입니다. 새로 시작하면 기록을 지우지 않고 새 세션을 만듭니다.

| API | 설명 |
|---|---|
| `POST /sessions` | 세션 생성. `previous_session_id`를 보내면 결제 없이 끝난 이전 세션을 `abandoned`로 닫음 |
| `POST /sessions/{id}/views` | 조회 저장 후 이 세션의 조회만으로 예측한 확률과 구매 의도 단계 반환. 단계는 `views.stage`에도 저장 |
| `POST /sessions/{id}/purchases` | 결제 저장, 세션을 `purchased`로 닫음 |
| `GET /sessions/{id}/predictions` | 결과 화면용 예측과 확률 변화(`timeline`) |
| `GET /dashboard` | 판매자 대시보드. 지금 쇼핑 중인 세션의 상품별 예상 구매, 단계별 인원, 자주 비교되는 상품 쌍 |

### 구매 의도 단계 (`stage`)

조회 API 응답의 `stage`는 사용자 맞춤 화면용입니다. 판단 규칙은 `ml/product_purchase/stage.py`에 있습니다.

```json
"stage": { "stage": "comparing", "items": ["A", "B"] }
```

| `stage` | 뜻 | `items` |
|---|---|---|
| `browsing` | 구경 중 | 빈 목록 |
| `comparing` | 고민 중 | 고민 중인 상품 2~3개 (비교 카드용) |
| `decided` | 살 마음 먹음 | 1위 상품 (구매 버튼 강조용) |
| `leaving` | 떠나려는 중 | 관심이 멀어지는 상품 (찜·가격 알림용) |

### 결과 화면 예측

구매하려면 상품 상세페이지를 거쳐야 해서, 구매 상품은 항상 마지막 조회가 됩니다. 이 조회까지 넣으면 "방금 본 상품"이라는 이유만으로 맞히게 되므로, 결과 API의 `prediction`은 결제하러 들어간 마지막 방문(끝에 연달아 있는 구매 상품 조회)을 빼고 계산합니다.

* `excluded_views`: 뺀 조회 수
* `prediction`: 빼고 나서 남는 조회가 없으면 `null`
* `timeline`: 확률 변화는 결제 직전까지 전체를 보여줌

### 판매자 대시보드 (`/dashboard`)

마지막 조회가 최근 30분 안에 있는 `active` 세션을 "지금 쇼핑 중"으로 보고 모읍니다. 계산 함수는 `ml/product_purchase/dashboard.py`에 있습니다.

```json
{
  "generated_at": "2026-10-29T14:03:00+00:00",
  "active_sessions": 23,
  "active_window_minutes": 30,
  "products": [
    { "item_id": "DRESS-01", "viewers": 4, "expected": 0.05, "low": 0, "high": 0,
      "at_least_one": 0.049, "purchased": 1, "stock": 8 }
  ],
  "stages": { "browsing": 8, "comparing": 6, "decided": 5, "leaving": 4 },
  "compare_pairs": [ { "items": ["BOTTOM-03", "BOTTOM-04"], "sessions": 1 } ],
  "insights": []
}
```

| 필드 | 뜻 | 범위 |
|---|---|---|
| `products[].viewers` | 이 상품을 본 고객 수 | 쇼핑 중 세션 |
| `products[].expected`, `low`, `high` | 예상 구매 수와 90% 범위 | 쇼핑 중 세션 |
| `products[].at_least_one` | 1명 이상 살 확률 (정렬 기준) | 쇼핑 중 세션 |
| `products[].purchased` | 실제 결제 수 | 전체 누적 |
| `products[].stock` | 가상 재고 (`backend/app/inventory.py`) | 고정값 |
| `stages` | 단계별 세션 수 | 쇼핑 중 세션 |
| `compare_pairs` | 고민 중 세션이 비교한 상품 쌍 (상위 10개) | 쇼핑 중 세션 |
| `insights` | 규칙 기반 안내 문장 (아래 참고) | |

* 상품 48개가 모두 나오며, 아무도 안 본 상품은 0으로 채웁니다. 상품 이름·사진·가격은 프론트가 `item_id`로 `products.js`에서 찾습니다.
* 예상 구매 수는 기간 단위가 아니라 "지금 보는 고객 중 결국 몇 명이 살지"입니다. 확률이 작아 대부분 0.1개 미만이므로 화면에서는 `at_least_one`이 읽기 쉽습니다.

#### 인사이트 (`insights`)

대시보드 숫자 중 확인해볼 만한 것을 규칙으로 골라 문장으로 만듭니다 (`backend/app/insights.py`). 원인(가격, 사진 등)은 데이터에 없어서 추측하지 않고 "확인해볼 점"으로만 씁니다.

```json
{ "type": "comparing_pair", "items": ["DRESS-05", "DRESS-06"],
  "message": "DRESS-05과(와) DRESS-06을(를) 함께 고민 중인 고객이 3명입니다. ..." }
```

| 순서 | `type` | 조건 |
|---|---|---|
| 1 | `low_stock` | 보는 고객이 있는데 품절이거나 남은 재고(재고 − 결제 수)가 1개 이하 |
| 2 | `comparing_pair` | 같은 상품 쌍을 고민 중인 세션 2개 이상 |
| 3 | `weak_intent` | 본 고객 3명 이상인데 살 마음 먹은 고객 없음 |
| 4 | `leaving` | 같은 상품에서 멀어지는 세션 2개 이상 |

* 종류별 최대 2개, 전체 최대 5개입니다.
* 쇼핑 중 고객이 5명 미만이면 `too_few_sessions` 안내와 재고 안내만 나옵니다.
* 기준 숫자는 `INSIGHT_THRESHOLDS`에 모여 있습니다.
* 프론트는 `items`로 상품 이름을 찾아 카드에 쓸 수 있습니다.

### 대시보드 확인용 가상 손님

서버를 띄운 상태에서 실행하면 실제 API로 가상 손님의 쇼핑 기록을 만듭니다. 확률과 단계는 모두 실제 모델로 계산됩니다.

```powershell
python backend/scripts/seed_dashboard.py --shoppers 30
```

* `--purchase-rate`: 결제하고 떠나는 손님 비율 (기본 0.3). 나머지는 쇼핑 중으로 남습니다.
* `--seed`: 같은 손님 구성을 다시 만들 때 지정
* 30분이 지나면 쇼핑 중에서 빠지므로 다시 실행하면 됩니다. 데이터를 지우려면 `docker compose down -v`
