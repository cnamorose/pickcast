\# Backend



FastAPI 기반 API 서버와 모델 추론 연동을 개발합니다.



\## 주요 기능



\* 체험 세션 관리

\* 상품 정보 제공 및 조회 이벤트 수집

\* 쇼핑 종료 시 모델 추론 실행

\* 최종 상품 선택 전 예측 결과 확정 및 저장

\* 가상 구매 결과 저장

\* 가상 결제 완료 후 예측과 실제 선택 비교 결과 제공



\## 개발 원칙



\* 최종 선택 정보가 모델 입력에 포함되지 않도록 합니다.

\* 학습과 서비스에서 동일한 피처 계산 규칙을 사용합니다.



\## 개발 환경



\* Python 3.13+

\* FastAPI

\* Uvicorn



\## 실행 방법



프로젝트 루트(`pickcast`)에서 실행합니다.



\### 1. 가상환경 활성화



PowerShell에서 다음 명령어를 실행합니다.



```powershell

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

backend\\venv\\Scripts\\Activate.ps1

```



\### 2. 패키지 설치



```powershell

pip install -r backend\\requirements.txt

```



\### 3. 서버 실행



```powershell

python -m uvicorn backend.app.main:app --reload

```



서버가 실행되면 다음 주소에서 API 문서를 확인할 수 있습니다.



`http://127.0.0.1:8000/docs`



