# Scorer

Phase 5 통합 스코어링 & 최종 선별 스킬.

## 역할

NUMR-V 가중 점수 산출, 임베딩 기반 24h 의미적 중복 제거, 상대+절대 하이브리드 등급 분류를 수행한다.

## 스크립트

| 파일 | 역할 |
|------|------|
| `numrv_scorer.py` | NUMR-V 가중합 계산 (N×0.10 + U×0.20 + M×0.20 + R×0.25 + V×0.25) |
| `dedup_engine.py` | ko-sroberta 임베딩 기반 24h 의미적 중복 탐지 (임계값 0.85) |
| `grade_classifier.py` | 상대+절대 하이브리드 등급 분류 (S/A/B/C/D) |

## NUMR-V 차원

- N(Novelty): 기존 서비스 대비 차별화 정도 (1~5)
- U(Urgency): 문제의 긴급성/반복성 (1~5)
- M(Market Demand): 프록시 지표 기반 시장 수요 (1~5)
- R(Revenue): 수익 모델 강도, ARPU 잠재력 (1~5)
- V(Validation): 시장 검증 결과 종합 (1~5)

## 등급 기준

| 등급 | 조건 |
|------|------|
| S | 배치 내 상위 10% AND NUMR-V ≥ 4.0 |
| A | 배치 내 상위 30% AND NUMR-V ≥ 3.2 |
| B | NUMR-V ≥ 2.5 |
| C | NUMR-V ≥ 1.5 |
| D | NUMR-V < 1.5 |

## 호출자

`run_engine.py` Phase 5에서 순차 호출:
1. Claude CLI → NUMR 상대 평가 (배치 전체 비교)
2. `NUMRVScorer.score_batch()` → 가중합
3. `DedupEngine.check_duplicates()` → 중복 제거
4. `GradeClassifier.classify()` → 등급 분류
