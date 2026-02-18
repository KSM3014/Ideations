# API Matcher

Phase 3 API 매칭 & 구현 검증 스킬.

## 역할

Phase 2 가설의 데이터 니즈를 임베딩 기반 의미적 매칭으로 API 카탈로그에서 찾고, 필드간 join 가능성을 분석하여 구현 가능성(%)을 산출한다.

## 스크립트

| 파일 | 역할 |
|------|------|
| `semantic_matcher.py` | ko-sroberta 임베딩 top-K 의미적 매칭 |
| `join_analyzer.py` | 2개+ API 간 공통 키(시군구코드, 날짜 등) join 분석 |
| `feasibility.py` | 구현 가능성 % 산출 (매칭 커버율 + API 수 + join 키) |

## 호출자

`run_engine.py` Phase 3에서 순차 호출:
1. `SemanticMatcher.match_hypothesis()` — 데이터 니즈별 top-K API
2. `JoinAnalyzer.analyze_api_pairs()` — API 쌍별 join 키
3. `FeasibilityCalculator.calculate()` — 종합 적합도

## 품질 게이트

- 적합도 ≥ 40% 통과 (`config.FEASIBILITY_PASS_THRESHOLD`)
- 매칭 API ≥ 2개, 필수 데이터 커버율 ≥ 50%
- 미통과 시 해당 가설 탈락

## 출력

가설별 `matched_apis`, `join_pairs`, `feasibility_pct`, `passed` 플래그.
