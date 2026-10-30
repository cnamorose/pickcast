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
- 원본 데이터, 전처리 결과, 실험·비교용 학습 모델은 Git에 올리지 않습니다.
- 서비스에 쓰는 확정 모델만 `ml/models/`에 버전별 폴더로 커밋합니다. 학습 데이터(RetailRocket)의 라이선스(CC BY-NC-SA 4.0)를 따릅니다.
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

학습에는 약 11분, 보정과 test 평가에는 각각 1분 안팎이 걸립니다. `evaluate_test.py`는 `test_metrics.json`이 이미 있으면 실행되지 않습니다. 공통 데이터 로드·가중치·평가 지표는 `product_purchase/modeling.py`에 있습니다.

서비스에 쓸 모델로 확정하면 `calibration.json`과 그 안의 `model`에 적힌 모델 파일을 새 버전 폴더(`ml/models/product_purchase_v2/` 등)로 복사하고, `metadata.json`을 함께 만들어 커밋합니다. 기존 버전 폴더는 덮어쓰지 않습니다.

#### 모델 버전 반영과 되돌리기

서비스가 쓸 버전은 `ml/models/current.json`이 정합니다. 백엔드는 몇 초마다 이 파일을 확인해 재시작 없이 새 버전을 불러옵니다(`backend/README.md`의 "모델 자동 교체"). 세션에 기록되는 `model_version`도 이 버전 이름이 됩니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/release.py list      # 버전 목록과 지금 쓰는 버전
.\ml\.venv\Scripts\python.exe ml/product_purchase/release.py use v2    # v2로 반영
.\ml\.venv\Scripts\python.exe ml/product_purchase/release.py use v1    # 되돌리기
```

모델 파일이 없는 등 쓸 수 없는 폴더로는 바뀌지 않습니다.

#### 재보정으로 새 버전 만들기

v1 모델을 valid 일반 고객 기준으로 다시 보정해 v2를 만듭니다. valid 일반 고객을 반으로 나눠 보정·평가하고, 등록 기준을 모두 통과해야 `ml/models/product_purchase_v2/`를 만듭니다. `current.json`은 바꾸지 않습니다. 결과는 [docs/ml/recalibration-v2.md](../docs/ml/recalibration-v2.md)에 정리했습니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/recalibrate.py
```

### 6. 조회 로그로 예측하기

서비스 연결에는 `product_purchase/predict.py`의 `PurchasePredictor`를 사용합니다. Git에 포함된 확정 모델(`ml/models/current.json`이 가리키는 버전 폴더의 `calibration.json`과 그 안의 `model`에 적힌 모델 파일)을 읽으므로 원본 데이터나 학습 과정 없이 바로 사용할 수 있습니다.

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

### 7. 구매 의도 단계 검증

사용자 맞춤 화면의 단계 판단(`product_purchase/stage.py`)이 실제 구매와 연결되는지 valid로 확인합니다. 학습 데이터가 있어야 하며, 결과는 [docs/ml/stage-validation.md](../docs/ml/stage-validation.md)에 정리했습니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/validate_stage.py          # 지금 기준값 (약 15초)
.\ml\.venv\Scripts\python.exe ml/product_purchase/validate_stage.py --grid   # 기준값 108개 조합 비교 (약 11분)
```

결과는 `ml/data/product_purchase/stage_validation.json`(그리드는 `stage_validation_grid.json`)에 저장됩니다.

기준값을 정한 뒤 확장 기능(단계별 구매율, 단순 규칙과의 1순위 비교, 대시보드 90% 범위 적중률)을 test로 한 번 확인합니다. 결과는 [docs/ml/extension-test-results.md](../docs/ml/extension-test-results.md)에 정리했습니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/evaluate_extension_test.py
```

`ml/data/product_purchase/models/extension_test_metrics.json`이 이미 있으면 실행되지 않습니다.

### 8. 체험 데이터로 학습 데이터 만들기

배치 재학습의 데이터 준비 단계입니다. 백엔드가 DB에서 내보낸 체험 기록 파일(CSV 또는 Parquet)을 학습 데이터로 바꿉니다. ml 코드는 DB에 직접 접속하지 않습니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/experience.py sessions.csv
```

| 단계 | 내용 |
| --- | --- |
| 입력 칸 | `session_id`, `event`(view/purchase), `item_id`, `timestamp`(ms), `status`, `kind`, `mode` |
| 정제 | 쇼핑 중인 세션, `mode`가 `experience`가 아닌 세션(가상 손님 등), 조회 100회 이상, 조회 간격 중앙값 1초 미만(조회 3회 이상일 때), 같은 기록 중복을 뺍니다 |
| 학습 행 | RetailRocket 학습 데이터와 같은 규칙(조회 시점 × 후보 상품, 피처 8개, 그 뒤 결제 여부). 고객 300명의 학습 행 15,855개를 기존 학습 데이터와 비교해 모두 같음을 확인했습니다 |
| 분리 | 세션 ID 해시로 학습(train) 80%, 평가(eval) 20% |
| 저장 | `ml/data/experience/<날짜>/training_rows.parquet`, `report.json`(뺀 세션 수와 이유). 같은 버전은 덮어쓰지 않습니다 |

#### 재학습 스위치 (`ml/pipeline_config.json`)

| 항목 | 뜻 | 기본 |
| --- | --- | --- |
| `retrain_enabled` | 체험 데이터로 재보정·재학습을 자동으로 돌릴지 | `false` |
| `auto_release` | 등록 기준을 통과한 새 버전을 서비스에 자동 반영할지. `false`면 등록만 하고 반영은 `release.py use`로 | `false` |
| `min_sessions` | 학습에 쓸 수 있는 체험 세션이 이만큼 쌓여야 재보정을 실행 | `50` |

배포 전에는 모두 꺼 둡니다. 배포 후 체험 데이터가 쌓이면 `retrain_enabled`를 켭니다. 스위치는 아래 파이프라인이 확인하며, 위의 학습 데이터 만들기나 직접 돌리는 `recalibrate.py`는 스위치와 상관없이 실행됩니다.

#### 재학습 파이프라인

백엔드가 내보낸 기록 파일 하나로 아래 단계를 한 번에 실행합니다. 어디서 멈췄는지와 숫자는 데이터셋 폴더의 `pipeline_report.json`에 남습니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/pipeline.py --build-reference              # 처음 한 번 (원본 데이터가 있는 곳에서)
.\ml\.venv\Scripts\python.exe ml/product_purchase/pipeline.py <기록 파일>                     # 스위치에 따라 실행
.\ml\.venv\Scripts\python.exe ml/product_purchase/pipeline.py <기록 파일> --dry-run           # 스위치와 상관없이 평가까지만
```

| 단계 | 내용 | 멈추는 경우 |
| --- | --- | --- |
| ① 스위치 | `retrain_enabled` 확인 | 꺼져 있음 (`--dry-run`은 건너뜀) |
| ② 학습 데이터 | 기록 파일 → 정제 → 학습 행 (`experience.py`) | |
| ③ 양 확인 | 학습용(train) 체험 세션 수 | `min_sessions` 미만 |
| ④ 재보정 | 지금 서비스 버전의 모델은 그대로 두고 보정만 다시 맞춤. RetailRocket 일반 고객 A 절반 + 체험 학습용, 체험 행 가중치 10 | |
| ⑤ 평가 | 체험 평가용(20%)에서 Log loss가 낮아지고 평균 예측과 실제의 차이가 커지지 않아야 함. RetailRocket B 절반에서 Log loss가 1% 넘게 나빠지지 않아야 함. 단계 판단 대표 흐름(`stage.STAGE_SCENARIOS`)이 모든 클릭 간격에서 의도한 단계로 나와야 함 | 기준 미통과 |
| ⑥ 등록 | 다음 번호의 버전 폴더 생성 (`release.py`의 `register_version`) | `--dry-run`이면 여기서 멈춤 |
| ⑦ 반영 | `auto_release`가 켜져 있으면 `current.json` 변경. 꺼져 있으면 `release.py use` 명령만 안내 | |

- RetailRocket 원본 학습 데이터는 배포 서버에 없으므로, 보정·비교에 쓰는 valid 일반 고객 행만 뽑은 참조 파일(`ml/data/product_purchase/pipeline_reference.parquet`, 약 15MB)을 `--build-reference`로 한 번 만들어 서버에 함께 둡니다. 고객을 A·B로 나누는 방법은 v2와 같습니다.
- 반영되면 실행 중인 백엔드가 몇 초 안에 새 버전을 씁니다. 내보내기와 파이프라인을 한 번에 돌리려면 `backend/scripts/run_retrain.py`를 씁니다.

### 9. 피크타임 우선 처리 시뮬레이션

서버가 몰렸을 때 구매 확률이 높은 고객부터 처리하면 선착순보다 산 고객을 더 지키는지, RetailRocket 기록을 재생해 비교합니다. α(에이징 계수)는 valid로 정하고 test로 한 번 확인합니다. 결과는 [docs/ml/peak-simulation.md](../docs/ml/peak-simulation.md)에 정리했습니다.

```powershell
.\ml\.venv\Scripts\python.exe ml/product_purchase/peak_simulation.py
```

- 결과 요약(`ml/results/peak_simulation.json`)은 백엔드 결과 API가 읽도록 Git으로 관리하고, 이미 있으면 실행되지 않습니다. 전체 결과는 `ml/data/product_purchase/peak_simulation.json`에 저장됩니다.
- 재생 화면용 파일은 `--replay-assets`로 만듭니다. test의 붐비는 시간대 5개 요청(`ml/results/peak_replay_windows.json`)을 저장하고 요약에 test α 곡선을 더하며, test를 다시 평가하지 않습니다. 백엔드 재생 API는 `replay()`로 시간대 하나를 재생해 도착·처리·이탈 사건을 받습니다.
- 학습 데이터(`ml/data/product_purchase/training_rows/`)가 있어야 실행됩니다.

### 10. 테스트

```powershell
.\ml\.venv\Scripts\python.exe -m unittest discover -s ml/product_purchase/tests -t ml/product_purchase -v
```

`test_features.py`는 손으로 만든 조회 기록으로 피처 정의를 확인합니다. `test_predict.py`는 Git에 포함된 확정 모델로 추론 결과의 형식과 일관성을 확인합니다. `test_release.py`는 임시 폴더로 버전 반영·되돌리기를 확인하고, `current.json`이 쓸 수 있는 버전을 가리키는지 확인합니다. `test_stage.py`의 시나리오 테스트는 `ml/models/`에 등록된 모든 버전으로 단계 판단을 확인하므로, 새 버전을 등록하면 단계 기준값이 그 버전에서도 통하는지 바로 드러납니다. `test_recalibrate.py`는 재보정의 등록 기준을 확인합니다. `test_experience.py`는 체험 기록 정제·학습 행·스위치를, `test_pipeline.py`는 임시 폴더와 가짜 체험 기록으로 파이프라인의 단계별 멈춤·등록·반영을 확인합니다. `test_peak_simulation.py`는 손으로 만든 요청으로 처리 순서, 이탈, 에이징을 확인합니다.