# 상품별 구매 예측 모델 v1

서비스(`ml/product_purchase/predict.py`)에서 사용하는 확정 모델이다. 학습 결과 중 서비스에 필요한 두 파일만 Git으로 관리한다.

| 파일 | 내용 |
| --- | --- |
| `lgbm_point.txt` | LightGBM 모델(예측 시점 가중치, 23회 반복) |
| `calibration.json` | 확률 보정(`isotonic_smooth`), 구매 판정 임계값(4.27%), valid 보정 지표 |

- 학습 데이터: RetailRocket `events.csv` 전체에서 만든 조회 시점별·후보 상품별 행
- 입력 피처: 조회 행동 8개(`ml/product_purchase/features.py`)
- test 성능(시점 가중): AP 0.0310(단순 기준 0.0092), ROC-AUC 0.700, 후보 1순위 정답률 31.7%(무작위 12.3%)
- 자세한 과정과 결과: [학습·보정·평가 결과](../../../docs/ml/product-purchase-model-results.md)

## 다시 만들기

`ml/README.md`의 4·5번 순서로 실행하면 `ml/data/product_purchase/models/`에 같은 파일이 생긴다. 그중 `calibration.json`과 그 안의 `model`에 적힌 모델 파일(`lgbm_point.txt`)을 이 폴더로 복사한다.

## 버전 관리

서비스 모델을 바꿀 때는 이 폴더를 덮어쓰지 않고 `product_purchase_v2/`처럼 새 폴더를 만든 뒤 `predict.py`의 `RELEASE_DIR`을 바꾼다. 어떤 모델로 어떤 결과를 냈는지 커밋 기록으로 추적하기 위해서다.

## 데이터 출처와 라이선스

이 모델은 Retailrocket이 공개한 [Retailrocket recommender system dataset](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset)(Kaggle)으로 학습했다. 데이터셋은 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 라이선스로 제공된다.

이 폴더의 모델 파일도 같은 **CC BY-NC-SA 4.0** 조건을 따른다.

- 출처(Retailrocket 데이터셋)를 표시한다.
- 비영리 목적으로만 사용한다.
- 이 모델을 변형해 공유할 때는 같은 라이선스를 적용한다.

원본 데이터와 학습 데이터는 용량이 커서 Git에 포함하지 않는다.
