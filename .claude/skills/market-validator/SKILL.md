# Market Validator

Phase 4 시장 검증 스킬.

## 역할

Phase 3 통과 가설에 대해 경쟁사 검색, 시장수요 프록시 평가, 타이밍/수익화/MVP 난이도를 검증하여 종합 점수(100점)를 산출한다.

## 스크립트

| 파일 | 역할 |
|------|------|
| `competitor_search.py` | Playwright 기반 경쟁 서비스 검색 |
| `market_proxy_scorer.py` | 시장수요 프록시 지표 평가 (유사 서비스 수, 커뮤니티 규모, 검색 추세) |
| `validation_scorer.py` | 5개 항목 종합 검증 점수 산출 (100점 만점) |

## 점수 배분

| 항목 | 배점 |
|------|------|
| 경쟁사 분석 | 25점 |
| 시장수요 프록시 | 25점 |
| 타이밍 적합성 | 20점 |
| 수익화 사례 | 15점 |
| MVP 난이도 | 15점 |

## 적응형 깊이

`TimeBudget.adaptive_depth()`가 가설 수와 잔여 시간에 따라 결정:
- deep (1~3개): 가설당 5분, Playwright 2~3회
- standard (4~6개): 가설당 3분, Playwright 1~2회
- light (7개+): 가설당 2분, Playwright 1회
- simplified (잔여 <10분): Claude 자체 지식 기반
- skipped (잔여 <5분): V=3 기본값

## 품질 게이트

검증 점수 ≥ 50점 통과 (`config.VALIDATION_PASS_THRESHOLD`).
