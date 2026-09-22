# ML

조회 행동 기반 구매 예측 모델을 개발하고 평가합니다.

## 주요 작업

- RetailRocket 데이터 정제 및 세션 구성
- 조회 행동 기반 피처 생성
- LightGBM 모델 학습
- 최다 조회·최근 조회 기준 모델과 성능 비교
- SHAP 기반 예측 설명
- 모델과 피처 정의의 버전 관리

## 개발 원칙

- 예측 시점 이후의 정보가 입력에 포함되지 않도록 합니다.
- 학습과 서버 추론에서 피처 계산 코드를 공유할 수 있도록 구성합니다.
- 공개 데이터의 실제 구매 예측과 웹 체험의 가상 선택 예측을 구분해 평가합니다.
- 원본 데이터, 전처리 결과, 학습 모델 파일은 Git에 올리지 않습니다.
- 데이터와 모델의 준비 방법 및 보관 위치를 문서에 기록합니다.

## 개발 환경

- 확인된 환경: Windows, Python 3.14.0
- 가상환경: venv
- 패키지 버전: `ml/requirements.txt` 참고

아래 명령은 모두 프로젝트 최상위 폴더에서 실행합니다.

### 1. 가상환경 생성 및 패키지 설치

Python 3.14가 설치된 환경에서 실행합니다.

```powershell
python -m venv ml/.venv
.\ml\.venv\Scripts\python.exe -m pip install -r ml/requirements.txt
```

가상환경의 Python 경로를 직접 사용하므로 별도의 활성화는 필요하지 않습니다.

### 2. 데이터 준비

RetailRocket 데이터셋의 `events.csv`를 내려받아 다음 위치에 배치합니다.

```text
ml/data/raw/events.csv
```

이번 학습에는 `events.csv`만 사용합니다.
원본 데이터와 가상환경 폴더는 Git에 커밋하지 않습니다.

### 3. 데이터 점검

```powershell
.\ml\.venv\Scripts\python.exe ml/scripts/inspect_events.py
```

행·열 개수, 데이터 예시, 컬럼별 자료형, 이벤트 분포,
결측치 및 완전히 동일한 중복 행 개수를 확인합니다.

현재는 데이터 점검 단계이며, 전처리와 모델 학습 명령은 구현 후 추가합니다.