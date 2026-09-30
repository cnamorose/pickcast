# ML

RetailRocket의 조회 행동을 바탕으로 상품별 구매 예측 모델을 개발합니다.

## 현재 상태
- [상품별 구매 예측 모델 v1 설계](../docs/ml/product-purchase-v1-spec.md)
- [첫 번째 실험: 30분 내 구매 예측](../docs/ml/within-30m-results.md) — 코드는 `experiments/within_30m/`에 있습니다.
- [두 번째 실험: 24시간 내 구매 예측](../docs/ml/within-24h-results.md) — 코드는 `experiments/within_24h/`에 있습니다.
- 두 실험은 초기에 구매 정답에 시간 제한이 필요하다고 판단해 진행한 실험입니다. 이후 본 모델은 시간 제한 없이 구매 여부를 정답으로 사용하기로 했으며, 실험 성능을 본 모델의 성능으로 사용하지 않습니다.
- 본 모델의 학습 데이터와 모델은 아직 만들지 않았습니다.

## 본 모델의 목표

사용자가 상품을 조회할 때마다 지금까지의 조회 로그를 반영해, 사용자가 본 상품 각각의 구매 예측 확률을 갱신합니다. 한 상품을 구매해도 다른 상품의 조회 기록은 초기화하지 않습니다.

조회 행동은 모델 입력에 사용하고 구매 기록은 정답을 만드는 데 사용합니다. 구매 정답에 30분·24시간 같은 고정된 시간 제한을 두지 않습니다.

## 개발 원칙

- 예측 시점 이후의 정보가 모델 입력에 포함되지 않도록 합니다.
- 학습과 실제 예측에서 같은 피처 계산 방식을 사용합니다.
- 원본 데이터, 전처리 결과, 학습 모델 파일은 Git에 올리지 않습니다.
- 데이터와 모델의 준비 방법 및 보관 위치를 문서에 기록합니다.

## 개발 환경

- 확인된 환경: Windows, Python 3.14.0
- 가상환경: venv
- 패키지 버전: `requirements.txt` 참고

아래 명령은 모두 프로젝트 최상위 폴더에서 실행합니다.

### 1. 가상환경 생성 및 패키지 설치

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

원본 데이터와 가상환경 폴더는 Git에 커밋하지 않습니다.

스크립트가 만드는 데이터와 모델도 `ml/data/` 아래에 로컬로만 보관합니다.

```text
ml/data/
  raw/events.csv                  원본 데이터
  experiments/within_30m/         30분 실험의 processed(학습 데이터)·artifacts(모델, 지표)
  experiments/within_24h/         24시간 실험의 processed·artifacts
```

본 모델의 데이터와 모델은 실험 결과와 섞이지 않도록 별도 폴더에 보관합니다.

### 3. 데이터 점검

```powershell
.\ml\.venv\Scripts\python.exe ml/scripts/inspect_events.py
```

이 스크립트로 데이터 크기, 컬럼, 이벤트 분포, 결측치와 동일한 행의 개수를 확인합니다. 현재 `ml/scripts/`에는 데이터 점검 스크립트가 있으며, 시간 제한 실험 코드는 `ml/experiments/`에 보관합니다.