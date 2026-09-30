# ML

RetailRocket의 조회 행동을 바탕으로 상품별 구매 예측 모델을 개발합니다.

## 현재 상태
- [상품별 구매 예측 모델 v1 설계](../docs/ml/product-purchase-v1-spec.md)
- [첫 번째 실험: 30분 내 구매 예측](../docs/ml/within-30m-results.md) — 코드는 `experiments/within_30m/`에 있습니다.
- [두 번째 실험: 24시간 내 구매 예측](../docs/ml/within-24h-results.md) — 코드는 `experiments/within_24h/`에 있습니다.
- 두 실험은 초기에 구매 정답에 시간 제한이 필요하다고 판단해 진행한 실험입니다. 이후 본 모델은 시간 제한 없이 구매 여부를 정답으로 사용하기로 했으며, 실험 성능을 본 모델의 성능으로 사용하지 않습니다.
- [본 모델 학습 데이터 생성 결과](../docs/ml/product-purchase-training-data.md) — 코드는 `product_purchase/`에 있습니다.
- [본 모델 학습·보정·평가 결과](../docs/ml/product-purchase-model-results.md) — v1 모델(LightGBM, 시점 가중치, isotonic_smooth 보정, 임계값 4.27%)을 확정하고 test를 평가했습니다.
- 서비스에서 쓸 추론 모듈(`product_purchase/predict.py`)을 추가했습니다. 백엔드 연결 방법은 [구매 예측 모델 연동 가이드](../docs/ml/product-purchase-inference-guide.md)에 정리했습니다.

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
  product_purchase/               본 모델의 사용자 분리, 학습 데이터, 생성 보고서
  product_purchase/models/        본 모델의 학습 모델, 보정, valid·test 지표
```

본 모델의 데이터와 모델은 실험 결과와 섞이지 않도록 `ml/data/product_purchase/`에 보관합니다. 학습 데이터는 행 수가 많아 Parquet 형식으로 저장합니다.

### 3. 데이터 점검

```powershell
.\ml\.venv\Scripts\python.exe ml/scripts/inspect_events.py
```

이 스크립트로 데이터 크기, 컬럼, 이벤트 분포, 결측치와 동일한 행의 개수를 확인합니다. 현재 `ml/scripts/`에는 데이터 점검 스크립트가 있으며, 시간 제한 실험 코드는 `ml/experiments/`에 보관합니다.

### 4. 본 모델 학습 데이터 생성

아래 순서로 실행합니다. 콘솔에서 한글이 깨지면 `$env:PYTHONIOENCODING = "utf-8"`을 먼저 설정합니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/split_users.py
.\ml\.venv\Scripts\python.exe ml/product_purchase/build_training_rows.py
.\ml\.venv\Scripts\python.exe ml/product_purchase/validate_training_rows.py
```

| 스크립트 | 하는 일 | 결과 (`ml/data/product_purchase/`) |
| --- | --- | --- |
| `split_users.py` | 사용자 단위 train/valid/test 70/15/15 분리 | `users.parquet`, `split_report.json` |
| `build_training_rows.py` | 조회 시점별·후보 상품별 피처와 정답 생성 | `training_rows/{train,valid,test}.parquet`, `build_report.json` |
| `validate_training_rows.py` | 샘플 시점을 원본에서 다시 계산해 대조 | 콘솔 출력 |

피처 계산은 `product_purchase/features.py`의 `UserViewState`에 있으며, 서비스 예측에서도 같은 클래스를 사용합니다. 전체 생성에는 약 2분이 걸립니다.

### 5. 본 모델 학습·보정·평가

학습 데이터를 만든 뒤 아래 순서로 실행합니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/train_models.py
.\ml\.venv\Scripts\python.exe ml/product_purchase/calibrate_model.py
.\ml\.venv\Scripts\python.exe ml/product_purchase/evaluate_test.py
```

| 스크립트 | 하는 일 | 결과 (`ml/data/product_purchase/models/`) |
| --- | --- | --- |
| `train_models.py` | 기준선과 LightGBM(가중치 row·point·user)을 학습하고 valid로 비교 | 모델 파일, `validation_metrics.json` |
| `calibrate_model.py` | 선택한 모델(`SELECTED_MODEL`)을 valid에서 보정하고 임계값 결정 | `calibration.json` |
| `evaluate_test.py` | 확정한 모델·보정·임계값으로 test를 한 번 평가 | `test_metrics.json` |

학습에는 약 11분, 보정과 test 평가에는 각각 1분 안팎이 걸립니다.

### 6. 조회 로그로 예측하기

서비스 연결에는 `product_purchase/predict.py`의 `PurchasePredictor`를 사용합니다. `ml/data/product_purchase/models/`의 확정 모델(`calibration.json`에 적힌 모델, 보정, 임계값)을 읽습니다.

```python
from predict import PurchasePredictor

predictor = PurchasePredictor()
views = [("2026-09-30T10:00:00", "셔츠"), ("2026-09-30T10:01:30", "청바지"), ...]
result = predictor.predict(views)     # 마지막 조회 시점의 후보별 확률·판정·순위·피처·SHAP 기여도
timeline = predictor.timeline(views)  # 조회마다 후보별 확률
```

- 입력은 `(timestamp, itemid)` 조회 기록입니다. timestamp는 밀리초 숫자 또는 날짜·시각 문자열, itemid는 숫자나 문자열 모두 가능합니다.
- 최종 선택·결제 정보는 입력에 넣지 않습니다. 이미 구매한 상품이 있으면 `purchases=[(timestamp, itemid)]`로 넘겨 후보에서 제외합니다.
- SHAP 기여도는 보정 전 모델 점수(로그 오즈)에 대한 값입니다. 기여 방향은 확률에도 그대로 적용되지만 합이 보정 확률과 같지는 않습니다.

CSV(`timestamp`, `itemid` 컬럼)로 결과를 바로 확인할 수도 있습니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/predict.py log.csv
```

### 7. 테스트

```powershell
.\ml\.venv\Scripts\python.exe -m unittest discover -s ml/product_purchase/tests -t ml/product_purchase -v
```

`test_features.py`는 손으로 만든 조회 기록으로 피처 정의를 확인합니다. `test_predict.py`는 추론 결과의 형식과 일관성을 확인하며, 로컬에 모델 파일이 없으면 건너뜁니다. `evaluate_test.py`는 `test_metrics.json`이 이미 있으면 실행되지 않습니다. 공통 데이터 로드·가중치·평가 지표는 `product_purchase/modeling.py`에 있습니다.