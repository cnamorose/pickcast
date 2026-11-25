# 상품별 구매 예측 모델 v3 (조회·장바구니·상품 통계)

판매자용 시뮬레이션·게임에서 쓰는 모델이다. 조회만 쓰는 v1·v2와 입력이 달라 `ml/product_purchase/predict_extended.py`로 불러온다 (`metadata.json`의 `input: view_cart`).

| 파일 | 내용 |
| --- | --- |
| `lgbm_point.txt` | LightGBM 모델(예측 시점 가중치, 54회 반복) |
| `calibration.json` | 확률 보정(`isotonic_smooth`), 구매 판정 임계값(14.36%), valid 보정 지표 |
| `item_stats.parquet` | 2015-05-03 ~ 06-30 기록으로 계산한 상품별 조회자 수·구매율·담기율 (162,894개) |
| `metadata.json` | 입력 피처 14개, 통계에 없는 상품의 기본값, 학습·보정·평가 데이터, test 성능 |

- 학습: 2015-05-03 ~ 06-30, 보정: 07-01 ~ 07-31. 두 기간 모두 기록이 그 기간 안에만 있는 사용자만 썼다.
- test(2015-08-01 ~ 09-18): AP 0.179(단순 기준 0.012), ROC-AUC 0.815, 정밀도 24.1%, 재현율 40.0%, 구매 직전 1순위 정답률 75.4%
- **8~9월 기록을 학습·보정에 쓰지 않았다.** 시뮬레이션·게임은 그 기간을 재생하므로, 시연에서 보이는 성능이 위 test 성능과 같다.
- 자세한 과정과 결과: [시간 분할 검증과 피처 실험](../../../docs/ml/time-split-results.md)

## 다시 만들기

`ml/README.md` 11절 순서로 피처 실험까지 실행한 뒤 아래를 실행한다. 이 폴더가 이미 있으면 실행되지 않는다.

```powershell
$env:PRODUCT_PURCHASE_DIR = "product_purchase_time"
.\ml\.venv\Scripts\python.exe ml/product_purchase/register_extended_model.py --version v3
```

## 서비스 반영

`current.json`은 아직 v2를 가리킨다. 지금 백엔드는 조회만 보내므로 v3를 반영하면 예측할 수 없다. 백엔드가 장바구니 기록을 받도록 바뀐 뒤 반영한다.

## 데이터 출처와 라이선스

[Retailrocket recommender system dataset](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset)(Kaggle)으로 학습했고, 데이터셋의 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 조건을 따른다. 상품 통계(`item_stats.parquet`)도 같은 데이터에서 가공한 것이므로 같은 조건을 따른다.
