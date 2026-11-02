# 프로젝트 문서

프로젝트 설계와 실험·평가 결과를 관리합니다. 브랜치·커밋·PR 규칙은 루트의 [협업 규칙](../CONTRIBUTING.md)을 참고합니다.

## ML 문서 (`ml/`)

### 구매 예측 모델

| 문서 | 내용 |
|---|---|
| [상품별 구매 예측 모델 v1 설계](ml/product-purchase-v1-spec.md) | 예측 대상, 정답 정의, 피처, 데이터 분리, 평가 계획 |
| [학습 데이터 생성 결과](ml/product-purchase-training-data.md) | 조회 시점별 후보 상품 데이터, 피처 정의, 사용자 단위 분리 |
| [학습·보정·평가 결과](ml/product-purchase-model-results.md) | 모델 비교와 선택, 확률 보정, 임계값, test 평가 |
| [모델 연동 가이드](ml/product-purchase-inference-guide.md) | 백엔드에서 추론 모듈(`predict.py`)을 쓰는 방법 |
| [모델 v2: 일반 고객 기준 재보정](ml/recalibration-v2.md) | 보정만 다시 맞춘 v2와 등록 기준 비교 (지금 서비스 버전) |

### 예측을 쓰는 기능

| 문서 | 내용 |
|---|---|
| [구매 의도 단계 판단 검증](ml/stage-validation.md) | 단계 판단 기준값과 단계별 실제 구매율 (valid) |
| [확장 기능 test 평가](ml/extension-test-results.md) | 단계 판단, 단순 규칙 대비 정답률, 대시보드 예상 범위 (test) |
| [피크타임 우선 처리 시뮬레이션](ml/peak-simulation.md) | 선착순·확률 우선·에이징 비교, α 선택 |

### 초기 실험 (본 모델 성능으로 쓰지 않음)

| 문서 | 내용 |
|---|---|
| [30분 내 구매 예측 학습 데이터 기준](ml/within-30m-spec.md), [결과](ml/within-30m-results.md) | 구매 정답에 30분 제한을 둔 첫 실험 |
| [24시간 내 구매 예측 결과](ml/within-24h-results.md) | 구매 정답에 24시간 제한을 둔 두 번째 실험 |

두 실험 뒤 본 모델은 구매 정답에 시간 제한을 두지 않기로 했습니다.

## 다른 README

- [루트 README](../README.md): 프로젝트 소개, 실행 방법, 결과 요약
- [ml/README](../ml/README.md): 학습·평가·재학습·시뮬레이션 실행 방법
- [backend/README](../backend/README.md): 서버 실행, API 설명
- [frontend/README](../frontend/README.md): 화면과 경로, 폴더 구조
