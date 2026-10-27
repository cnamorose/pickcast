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
| `POST /sessions/{id}/views` | 조회 저장 후 이 세션의 조회만으로 예측한 확률과 `stage` 반환 (`stage`는 현재 임시값) |
| `POST /sessions/{id}/purchases` | 결제 저장, 세션을 `purchased`로 닫음 |
| `GET /sessions/{id}/predictions` | 결과 화면용 예측과 확률 변화(`timeline`) |
| `POST /predictions` | 기존 체험용. 프론트가 세션 API로 옮긴 뒤 삭제 예정 |
