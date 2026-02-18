# Signal Collector

Phase 1 외부 신호 수집 스킬.

## 역할

실시간 외부 신호(트렌드, 뉴스, 테크, 정책, 펀딩)를 Playwright 브라우저 자동화로 크롤링하고, 라운드로빈 방식으로 소스를 선택하여 통합 신호 JSON을 산출한다.

## 스크립트

| 파일 | 역할 |
|------|------|
| `crawl_trends.py` | Google Trends KR 실시간 트렌드 크롤링 |
| `crawl_news.py` | Google News 한국어 뉴스 크롤링 |
| `crawl_tech.py` | ProductHunt / Hacker News 크롤링 |
| `crawl_policy.py` | 정부24 / 법제처 정책 브리핑 크롤링 |
| `crawl_funding.py` | 스타트업 투자/펀딩 뉴스 크롤링 |
| `signal_aggregator.py` | 라운드로빈 소스 선택, URL 캐시, 타임아웃 관리, 통합 |

## 호출자

`run_engine.py` Phase 1에서 `signal_aggregator.collect_signals()` 호출.

## 소스 로테이션

- 항상 실행: Google Trends
- 라운드로빈: 뉴스, 테크, 정책, 펀딩 중 2개
- URL 캐시: 24시간 TTL
- 소스별 타임아웃: 3분

## 출력

`output/signals/{timestamp}_signals.json` — 각 신호에 source, title, url, snippet, collected_at 포함.

## 실패 처리

모든 소스 실패 시 빈 리스트 반환. Phase 2는 카탈로그 기반으로 계속 진행.
