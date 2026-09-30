# 구매 예측 모델 연동 가이드 (백엔드용)

체험 서비스 백엔드에서 상품별 구매 예측 모델을 호출하는 방법을 정리한 문서다. 모델이 어떻게 만들어졌는지는 [학습·평가 결과](product-purchase-model-results.md)를 참고한다.

## 1. 한눈에 보기

- 사용자의 **조회 로그**(시각, 상품 ID)를 넘기면, 사용자가 본 **상품마다** 구매 확률, 판정, 순위, 피처 값, SHAP 기여도를 돌려준다.
- 조회 로그를 한 건씩 재생하며 **조회할 때마다 확률이 어떻게 바뀌었는지**도 돌려줄 수 있다.
- 파이썬 모듈 `ml/product_purchase/predict.py`의 `PurchasePredictor` 클래스를 import해 사용한다. 별도 모델 서버는 없다.

```python
predictor = PurchasePredictor()                  # 서버 시작 시 한 번
result = predictor.predict(views)                # 쇼핑 종료 시: 최종 예측
timeline = predictor.timeline(views)             # 확률 변화 그래프용
```

## 2. 준비물

### 코드와 패키지

- `ml/product_purchase/`의 `predict.py`, `features.py`, `modeling.py`, `events.py`
- 패키지: `numpy`, `pandas`, `lightgbm`, `scikit-learn`, `pyarrow` (버전은 `ml/requirements.txt`)

### 모델 파일 (Git에 없음)

아래 두 파일이 필요하다. ML 담당에게 받거나, `ml/README.md` 4·5번 순서로 직접 생성한다(원본 데이터 필요, 약 15분).

| 파일 | 내용 |
| --- | --- |
| `calibration.json` | 사용할 모델 이름, 확률 보정 곡선, 구매 판정 임계값 |
| `lgbm_point.txt` | LightGBM 모델 |

기본 위치는 `ml/data/product_purchase/models/`이다. 다른 곳에 두려면 `PurchasePredictor(directory="경로")`로 지정한다.

### 불러오기

모듈들이 같은 폴더 안에서 서로를 import하므로 `ml/product_purchase`를 import 경로에 추가한다.

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("ml/product_purchase").resolve()))
from predict import FEATURE_LABELS, PurchasePredictor
```

## 3. 입력

```python
views = [
    ("2026-09-30T10:00:00", "shirt-01"),
    ("2026-09-30T10:01:30", "jeans-02"),
    ("2026-09-30T10:04:00", "shirt-01"),
]
```

- `(timestamp, itemid)` 목록, 또는 `timestamp`, `itemid` 컬럼이 있는 pandas DataFrame
- `timestamp`: 밀리초 단위 숫자(epoch ms) 또는 날짜·시각 문자열. **초 단위 숫자를 넣으면 경과 시간이 1000배 틀어지므로** 숫자는 반드시 밀리초로 넘긴다.
- `itemid`: 숫자·문자열 모두 가능. 출력에 그대로 돌려준다. 모델은 상품 ID 자체를 입력으로 쓰지 않으므로 체험용 상품 ID를 그대로 써도 된다.
- 순서는 상관없다. 내부에서 시간순으로 정렬한다. 같은 시각의 조회는 하나의 예측 시점으로 묶는다.
- **조회(view)만 넣는다.** 장바구니, 최종 선택, 결제 정보는 넣지 않는다. 최종 선택이 입력에 들어가면 예측이 아니게 된다.
- 체험 중 이미 구매한 상품이 있다면 `predict(views, purchases=[(timestamp, itemid)])`로 넘긴다. 해당 상품은 후보에서 빠지고 `purchased`로 돌려준다. 다른 상품의 조회 기록은 그대로 유지된다.
- 조회 기록이 비어 있으면 `ValueError`가 난다.

## 4. 출력

### `predict(views)`: 마지막 조회 시점의 최종 예측

```json
{
  "predicted_at": 1790762640000,
  "threshold": 0.04265931570133532,
  "candidates": [
    {
      "item_id": "shirt-01",
      "probability": 0.022962829361610194,
      "decision": "미구매 예상",
      "rank": 1,
      "features": {
        "view_count": 2.0,
        "view_share": 0.6666666865348816,
        "seconds_since_first_view": 240.0,
        "seconds_since_last_view": 0.0,
        "revisit_count": 1.0,
        "user_total_views": 3.0,
        "distinct_items_viewed": 2.0,
        "is_last_viewed": 1.0
      },
      "shap": {
        "base_value": -5.118819443347396,
        "contributions": {
          "view_count": 0.3610471176132075,
          "view_share": -0.15083331420905421,
          "seconds_since_first_view": 0.15621123252457583,
          "seconds_since_last_view": 0.9497148475801693,
          "revisit_count": -0.056705963596803036,
          "user_total_views": -0.060215025349163585,
          "distinct_items_viewed": -0.10886986114359061,
          "is_last_viewed": 0.02042091744157286
        }
      }
    }
  ],
  "purchased": []
}
```

위 예시는 실제 출력에서 첫 번째 후보만 남긴 것이다. `candidates`는 확률이 높은 순서로 정렬되어 있다.

| 필드 | 설명 |
| --- | --- |
| `predicted_at` | 예측 기준 시각(밀리초). 마지막 조회 시각이다. |
| `threshold` | 구매 판정 임계값(현재 약 4.27%) |
| `candidates[].item_id` | 입력한 상품 ID 그대로 |
| `candidates[].probability` | 보정된 구매 확률(0~1). 화면에는 퍼센트로 표시한다. |
| `candidates[].decision` | `probability >= threshold`이면 `구매 예상`, 아니면 `미구매 예상` |
| `candidates[].rank` | 후보 중 확률 순위(1부터) |
| `candidates[].features` | 모델 입력 피처 값 |
| `candidates[].shap.contributions` | 피처별 기여도. 양수는 확률을 올린 요인, 음수는 내린 요인 |
| `candidates[].shap.base_value` | 기여도의 기준값 |
| `purchased` | `purchases`로 넘겨 후보에서 제외한 상품 |

조회한 상품을 모두 구매했다면 `candidates`는 빈 목록이다.

### `timeline(views)`: 조회마다 확률 변화

```json
[
  {"timestamp": 1790762400000, "viewed": ["shirt-01"], "probabilities": {"shirt-01": 0.0055}},
  {"timestamp": 1790762490000, "viewed": ["jeans-02"], "probabilities": {"shirt-01": 0.0061, "jeans-02": 0.0061}},
  {"timestamp": 1790762640000, "viewed": ["shirt-01"], "probabilities": {"shirt-01": 0.0230, "jeans-02": 0.0079}}
]
```

예측 시점(같은 시각의 조회 묶음)마다 하나씩 기록한다. 마지막 원소의 확률은 `predict` 결과와 같다. 셔츠를 다시 보자 셔츠 확률이 0.55% → 2.30%로 오르는 식의 변화를 그래프로 보여줄 수 있다.

## 5. 화면 표시 시 주의할 점

### 피처 이름

화면에 표시할 한글 이름은 `predict.py`의 `FEATURE_LABELS`에 있다.

| 피처 | 표시 이름 |
| --- | --- |
| `view_count` | 조회 횟수 |
| `view_share` | 전체 조회 중 비중 |
| `seconds_since_first_view` | 첫 조회 후 경과 시간 |
| `seconds_since_last_view` | 마지막 조회 후 경과 시간 |
| `revisit_count` | 다른 상품을 본 뒤 재방문 횟수 |
| `user_total_views` | 전체 조회 수 |
| `distinct_items_viewed` | 조회한 상품 수 |
| `is_last_viewed` | 가장 최근에 본 상품 |

`seconds_since_*`를 "페이지 체류 시간"이라고 표시하지 않는다. 조회 사이의 시간 차이일 뿐이다.

### SHAP 기여도

- 기여도는 **보정 전 모델 점수(로그 오즈)** 기준이다. `base_value + 기여도 합`은 보정 전 점수이고, 보정 확률(`probability`)과 합이 맞지 않는다.
- 보정은 점수가 높을수록 확률도 높아지는 단조 변환이므로, **기여 방향(올림/내림)과 크기 순서는 확률에도 그대로 적용된다.**
- 화면에는 "확률 2.3%"와 "올린 요인 / 내린 요인"을 나눠 보여주고, 기여도 숫자를 퍼센트포인트처럼 표시하지 않는다.

### 확률의 크기

- 확률은 대부분 **1% 안팎**이다. 모델이 학습한 공개 데이터의 실제 구매 비율이 약 0.9%이기 때문이며, 확률 자체는 실제 구매 비율과 잘 맞는다.
- 그래서 `구매 예상`(4.27% 이상) 판정은 드물게 나온다.
- 체험에서는 사용자가 반드시 하나를 고르므로, 선택한 상품의 확률이 1~2%로 보이면 어색할 수 있다. 예측과 실제 선택의 비교는 **순위**("AI 1순위 = 실제 선택?")나 **평균 대비 배수**(예: 평균 0.9% 대비 2.5배) 중심 표시를 권장한다. 이 부분은 프론트엔드와 함께 정한다.
- 보기 좋게 만들기 위해 확률을 임의로 키우거나 바꾸지 않는다(설계 원칙).

### 상품을 하나만 본 경우

첫 조회 시점에는 모든 상품의 피처가 같아 확률도 항상 같다(약 0.55%). 상품을 하나만 보고 끝냈다면 "조회 기록이 더 쌓여야 상품별 차이가 생긴다"는 안내가 필요하다.

## 6. 운영 시 참고

- `PurchasePredictor()`는 **서버 시작 시 한 번만** 만들고 재사용한다(로딩 약 11ms).
- 호출 사이에 상태를 공유하지 않으므로 여러 요청에서 같은 인스턴스를 동시에 써도 된다.
- 측정한 소요 시간(조회 60건, 상품 20개): `predict` 약 16ms, `timeline` 약 106ms. `timeline`은 조회 수에 비례해 느려지므로 필요한 화면에서만 호출한다.
- 모델을 다시 학습하면 `calibration.json`의 임계값과 보정 곡선도 바뀐다. 임계값을 백엔드에 하드코딩하지 말고 응답의 `threshold`를 사용한다.

## 7. FastAPI 연동 예시

아래는 호출 방식을 보여주는 예시다. 경로, 요청 형식, 세션 저장 방식은 백엔드 설계에 맞게 바꾼다.

```python
import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, str(Path("ml/product_purchase").resolve()))
from predict import FEATURE_LABELS, PurchasePredictor

app = FastAPI()
predictor = PurchasePredictor()


class ViewEvent(BaseModel):
    timestamp: int  # epoch milliseconds
    item_id: str


class PredictRequest(BaseModel):
    views: list[ViewEvent]


@app.post("/predictions")
def predict(request: PredictRequest):
    views = [(v.timestamp, v.item_id) for v in request.views]
    return {
        "prediction": predictor.predict(views),
        "timeline": predictor.timeline(views),
        "feature_labels": FEATURE_LABELS,
    }
```

## 8. 확인 방법

- 단위 테스트: `.\ml\.venv\Scripts\python.exe -m unittest discover -s ml/product_purchase/tests -t ml/product_purchase -v`
- CSV로 결과 보기: `timestamp`, `itemid` 컬럼 CSV를 만들고 `.\ml\.venv\Scripts\python.exe ml/product_purchase/predict.py log.csv`
- 학습 데이터와 추론 결과가 같은지 test 사용자 200명(4,011행)으로 확인했다(차이 0).

## 관련 문서

- [상품별 구매 예측 모델 v1 설계](product-purchase-v1-spec.md)
- [학습·보정·평가 결과](product-purchase-model-results.md)
- [ml/README](../../ml/README.md): 모델 파일 생성 방법
