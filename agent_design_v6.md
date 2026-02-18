# API Ideation Engine v6.0 — 에이전트 시스템 설계서

> Claude Code 기반 심층 추론 아이디어 엔진  
> 작성일: 2026-02-18  
> 상태: 설계 초안 (리뷰 대기)

---

## 1. 작업 컨텍스트

### 1.1 배경

기존 v5.0 엔진은 data.go.kr의 10,000+ 공공 API를 SQLite에 수집하고, 랜덤 조합 → 정적 템플릿 seed → LLM 재포장 → NUMR 스코어링 파이프라인으로 아이디어를 생성한다. 그러나 다음 근본적 한계가 확인됨:

| 문제 | 원인 (코드 레벨) |
|------|-----------------|
| 아이디어가 피상적 | `_build_seed_idea()`가 `CATEGORY_TO_DOMAIN` → `DOMAIN_SERVICE_TYPE` 1:1 정적 매핑. 도메인이 같으면 서비스 유형이 항상 동일 |
| API 조합이 억지스러움 | 랜덤 mix 선택 후 의미적 연결성 검증 없음. "OECD시험가이드라인 → 시군구코드" 같은 무관한 매칭 발생 |
| 중복/유사 반복 | daily report에서 동일 아이디어가 3개 배치에 연속 등장. 중복 회피가 시그니처 기반이라 의미적 유사도 미검출 |
| 수익모델이 뻔함 | `DOMAIN_REVENUE_MODEL` 딕셔너리가 도메인당 1개 고정. "B2B SaaS 구독" 반복 |
| LLM 정제가 무의미 | gpt-4.1-mini가 이미 고정된 seed 구조를 받아 재포장만 수행. 실제로는 API 키 부재로 LLM 호출 자체가 비활성 |

### 1.2 목적

**data.go.kr의 모든 공공 API 파라미터와 데이터를 의미적으로 조합하여, 바로 구현 가능한 서비스 아이디어를 산출**하는 에이전트 시스템을 완전 재설계한다.

핵심 혁신:
1. **역방향 추론**: "이런 서비스를 만들려면 이런 데이터가 필요하다" → API 카탈로그에서 매칭 (기존: 랜덤 API 조합 → 서비스 끼워맞추기)
2. **시장 검증 통합**: 경쟁사 분석, 시장수요 프록시 지표, 타이밍 적합성, 수익화 사례를 스코어링에 통합
3. **실시간 외부 신호**: 트렌드/뉴스/정책/펀딩 데이터가 아이디어 생성을 트리거
4. **Python + Claude CLI 하이브리드**: Python 오케스트레이터가 전체 파이프라인 제어, Claude CLI를 통한 LLM 심층 추론으로 가설 생성

### 1.3 범위

| 포함 | 제외 |
|------|------|
| 아이디어 생성 파이프라인 완전 재설계 | 실제 MVP 구현/배포 |
| 새 스코어링 체계 (NUMR + 시장검증) | 사용자 계정/인증 시스템 |
| 대시보드 대폭 개선 (시장분석 리포트) | 모바일 앱 |
| Discord 웹훅 고급화 | Discord Bot (웹훅 유지) |
| 기존 SQLite DB 재사용 + 스키마 확장 | DB를 PostgreSQL 등으로 마이그레이션 |
| 주간 카탈로그 자동 갱신 | 실시간 API 응답 모니터링 |

### 1.4 입출력 정의

**입력:**
- `data/public_api_catalog.sqlite3` — 10,000+ 공공 API 메타데이터, 파라미터, 오퍼레이션
- 실시간 외부 신호 (Playwright 크롤링):
  - Google Trends / 뉴스 검색
  - ProductHunt / TechCrunch / Hacker News
  - 정부 정책 브리핑 / 법령정보
  - 스타트업 투자/펀딩 뉴스
- 기존 아이디어 아카이브 (`ideas_archive.jsonl`)
- 사용자 피드백 (대시보드 게시/보류/제외 상태)

**출력:**
- 품질 기준 통과 아이디어 (개수 적응형, 0~N개)
- 각 아이디어에 포함되는 정보:
  - 서비스 가설 (문제 → 솔루션 → 타깃 → 수익모델)
  - API 구현 설계 (필요 데이터 → 매칭 API → join 경로)
  - 시장 검증 리포트 (경쟁사, 시장수요 프록시, 차별화, 타이밍)
  - MVP 난이도 추정 (주 단위)
  - 실제 API 응답 샘플 데이터 검증 결과
  - 통합 스코어 (NUMR-V)
- 대시보드 배치 (시장분석 리포트 형태)
- Discord 웹훅 알림 (S급 이상, 리치 embed)
- 일간/주간 누적 리포트

### 1.5 주요 제약조건

| 제약 | 영향 |
|------|------|
| **API 키 없음** — 구독만 사용 | 모든 LLM 호출은 Claude Code CLI (`claude -p`), 웹 검색은 Playwright 브라우저 자동화 |
| **Claude Max 구독** | `claude -p` 무제한 배치 호출 가능. 매시 다수 호출 허용 |
| **ChatGPT Pro + Codex** | Codex를 스크립트 코드 생성/개선에 지속적 활용. Claude Code가 추론 엔진 전담 |
| **Windows PC 24/7** | 작업 스케줄러 + PowerShell 기반 실행 |
| **매시 정각 실행** | 1시간 내 완료 필수. Playwright 크롤링 + Claude 추론 포함 |
| **기존 DB 재사용** | SQLite 스키마 확장은 가능하나, 기존 데이터 보존 |

### 1.6 용어 정의

| 용어 | 정의 |
|------|------|
| **역방향 추론** | 서비스 가설을 먼저 구상하고, 필요한 데이터를 도출한 뒤 API 카탈로그에서 매칭하는 방식 |
| **NUMR-V** | Novelty(신선도) × Urgency(필요도) × Market(시장규모) × Revenue(수익성) + Validation(시장검증) 통합 스코어 |
| **시장 검증** | 웹 크롤링을 통한 경쟁사 존재 확인, 시장수요 프록시 지표 평가, 타이밍 적합성 평가, 수익화 사례 참조 |
| **외부 신호** | 트렌드, 뉴스, 정책 변화, 펀딩 등 실시간 맥락 데이터 |
| **품질 게이트** | 각 파이프라인 단계의 통과 기준. 미통과 시 해당 아이디어 탈락 |

---

## 2. 워크플로우 정의

### 2.1 전체 파이프라인 개요

```
매시 정각 트리거
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: 맥락 수집 (5~10분)                                 │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │ 트렌드   │  │ 뉴스     │  │ 정책변화  │  │ 펀딩/스타트업│ │
│  │ (Google) │  │ (검색)   │  │ (법령정보)│  │ (Crunchbase) │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘ │
│       └──────────────┴──────────────┴──────────────┘         │
│                          │                                    │
│                   외부 신호 요약                                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: 역방향 가설 생성 (10~15분)                          │
│                                                               │
│  Claude Code 추론:                                            │
│  "외부 신호 + API 카탈로그 도메인 지식"                          │
│       → "이런 서비스가 지금 필요하다"                             │
│       → "이 서비스에는 이런 데이터가 필요하다"                     │
│       → "이 데이터는 이 API들에서 가져올 수 있다"                  │
│                                                               │
│  출력: 후보 가설 8~15개 (JSON)                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: API 매칭 & 구현 검증 (5~10분)                       │
│                                                               │
│  스크립트 처리:                                                │
│  - 필요 데이터 → SQLite 카탈로그 의미적 매칭                     │
│  - 필드간 join 가능성 분석                                      │
│  - 실제 API 응답 샘플 데이터 존재 여부 확인                       │
│  - 구현 가능성 % 산출                                           │
│                                                               │
│  품질 게이트: 구현 가능성 ≥ 40% 통과                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: 시장 검증 (10~20분)                                 │
│                                                               │
│  Playwright 크롤링 + Claude 추론:                              │
│  - 경쟁 서비스 존재 여부 및 차별화 포인트                         │
│  - 시장수요 프록시 지표 평가                                      │
│  - 타이밍 적합성 (트렌드 부합, 정책 방향)                         │
│  - 유사 수익화 사례 참조                                        │
│  - MVP 구현 난이도 추정 (주 단위)                                │
│                                                               │
│  품질 게이트: 시장 검증 점수 ≥ 50/100                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 5: 통합 스코어링 & 최종 선별 (2~5분)                    │
│                                                               │
│  NUMR-V 스코어링:                                              │
│  - N(신선도) + U(필요도) + M(시장규모) + R(수익성)               │
│  - V(Validation) = 시장 검증 점수 통합                          │
│  - 24h 의미적 중복 제거                                         │
│  - 품질 기준 통과한 것만 산출 (개수 적응형)                       │
│                                                               │
│  등급: S(즉시실행) / A(고수익) / B(보통) / C(피벗필요) / D(보류)  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 6: 산출물 기록 & 알림 (1~2분)                           │
│                                                               │
│  - 대시보드 배치 기록 (시장분석 리포트 형태)                      │
│  - S급 이상 Discord 웹훅 발송 (리치 embed)                      │
│  - 일간 누적 리포트 갱신                                        │
│  - 아카이브 저장                                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 단계별 상세

#### Phase 1: 맥락 수집

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (Playwright 브라우저 자동화) |
| **입력** | 없음 (외부 소스 직접 크롤링) |
| **출력** | `output/signals/{timestamp}_signals.json` |
| **성공 기준** | 4개 소스 중 최소 2개에서 유효 신호 수집 |
| **검증 방법** | 스키마 검증 — 필수 필드(source, title, summary, relevance_score) 존재 |
| **실패 처리** | 스킵 + 로그. 신호 0개여도 Phase 2는 카탈로그 기반으로 진행 |

**수집 소스별 전략:**

| 소스 | 크롤링 대상 | 추출 정보 | 예상 소요 |
|------|------------|----------|----------|
| Google Trends | `trends.google.co.kr` 실시간 트렌드 | 상위 키워드, 관련 쿼리 | 1~2분 |
| 뉴스 | Google News 한국어 | 제목, 요약, 카테고리 | 1~2분 |
| 테크 트렌드 | ProductHunt, Hacker News | 신규 서비스, 기술 키워드 | 2~3분 |
| 정책 변화 | 정부24, 법제처 | 신규/개정 법령, 정책 브리핑 | 1~2분 |
| 펀딩 | Crunchbase 뉴스, 매경/한경 스타트업 | 최근 투자, 분야, 금액 | 1~2분 |

**수집 최적화:**
- 전체 소스를 매시 크롤링하지 않고, 라운드 로빈 방식으로 배분
- 매시: Google Trends(항상) + 나머지 4개 중 2개 로테이션
- 캐시: 동일 URL 24시간 내 재방문 방지
- 타임아웃: 소스당 최대 3분, 초과 시 스킵

#### Phase 2: 역방향 가설 생성

| 항목 | 내용 |
|------|------|
| **처리 주체** | Claude Code CLI (`claude -p`) — LLM 추론 |
| **입력** | 외부 신호 요약 + API 카탈로그 도메인 요약 + 최근 24h 아카이브 (중복 회피) |
| **출력** | `output/hypotheses/{timestamp}_hypotheses.json` |
| **성공 기준** | 유효 가설 8개 이상 생성, 각 가설에 필수 필드 완비 |
| **검증 방법** | 스키마 검증 + LLM 자기 검증 (생성된 가설의 논리적 일관성) |
| **실패 처리** | 자동 재시도 (최대 2회, 프롬프트 변형). 3회 실패 시 에스컬레이션 로그 |

**역방향 추론 프로세스:**

```
Step 2-1: 기회 영역 식별 (Claude 판단)
  입력: 외부 신호 + 카탈로그 도메인 분포
  출력: "지금 이 분야에서 이런 문제를 해결하면 가치 있다" × 10~20개 방향

Step 2-2: 서비스 가설 구체화 (Claude 판단)
  입력: 기회 영역 + "실제로 돈을 내는 구매자는 누구인가" 관점
  출력: 서비스명, 문제정의, 솔루션 컨셉, 타깃 구매자, 수익모델 × 8~15개

Step 2-3: 필요 데이터 도출 (Claude 판단)
  입력: 서비스 가설 각각
  출력: "이 서비스를 구현하려면 이런 데이터 필드가 필요하다" — 4~10개 데이터 니즈

Step 2-4: API 예비 매칭 제안 (Claude 판단 + 카탈로그 참조)
  입력: 데이터 니즈 + 카탈로그 카테고리/API 목록 요약
  출력: "이 데이터는 이 API에서 가져올 수 있을 것" — 예비 매칭 제안
```

**프롬프트 설계 원칙:**
- 카탈로그 전체를 프롬프트에 넣지 않음 (토큰 폭발 방지)
- 대신 **카테고리별 API 수 + 대표 파라미터 키워드 요약**을 사전 생성하여 참조
- "존재하지 않는 API를 상상하지 마라" 제약 명시
- 최근 24h 생성된 서비스명/타깃/유형 목록을 제공하여 중복 회피

#### Phase 3: API 매칭 & 구현 검증

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (Python, SQLite 쿼리) |
| **입력** | Phase 2 가설의 데이터 니즈 목록 |
| **출력** | 가설별 매칭 결과 (matched_apis, missing_data, feasibility_pct) |
| **성공 기준** | 구현 가능성 ≥ 40% |
| **검증 방법** | 규칙 기반 — 매칭된 API 수 ≥ 2, 필수 데이터 커버율 ≥ 50% |
| **실패 처리** | 해당 가설 탈락 (스킵 + 로그) |

**기존 대비 개선점:**
- **의미적 매칭 강화**: 현재 `search_need()`의 토큰 매칭을 넘어, 파라미터 설명문 기반 유사도 스코어링
- **필드간 join 분석**: 2개 이상 API를 조합할 때, 공통 키(시군구코드, 날짜, 사업자번호 등)로 join 가능한지 검증
- **API 응답 샘플 검증**: data.go.kr 미리보기 또는 실제 호출로 데이터 품질 확인 (주간 배치에서 수행, 결과 캐시)

#### Phase 4: 시장 검증

| 항목 | 내용 |
|------|------|
| **처리 주체** | Playwright (크롤링) + Claude Code CLI (분석) |
| **입력** | Phase 3 통과한 가설 목록 |
| **출력** | 가설별 시장 검증 리포트 |
| **성공 기준** | 시장 검증 점수 ≥ 50/100 |
| **검증 방법** | LLM 자기 검증 — 검증 리포트의 근거 충실도 평가 |
| **실패 처리** | 해당 가설 탈락 (스킵 + 로그). 전체 탈락 시 Phase 2 재시도 |

**시장 검증 항목:**

| 항목 | 방법 | 점수 배분 |
|------|------|----------|
| **경쟁사 분석** | Playwright로 Google 검색 → Claude가 경쟁 서비스 파악 및 차별화 포인트 도출 | 25점 |
| **시장 수요 프록시** | 유사 서비스 존재 수, 타깃 사용자 커뮤니티 규모, 검색량 추세 등 검증 가능한 프록시 지표로 시장 수요 평가 (LLM 할루시네이션 방지를 위해 수치적 TAM 추정 대신 채택) | 25점 |
| **타이밍 적합성** | 외부 신호(트렌드, 정책)와의 부합도 | 20점 |
| **수익화 사례** | 유사 서비스의 수익화 모델과 실적 참조 | 15점 |
| **MVP 난이도** | 구현 복잡도, 필요 인력, 예상 기간(주) 추정 | 15점 |

**비용 최적화:**
- Phase 3 통과 가설만 시장 검증 수행 (전체의 30~50% 예상)
- 가설당 웹 검색 2~3회로 제한
- 유사 키워드 검색은 묶어서 1회에 처리

#### Phase 5: 통합 스코어링 & 최종 선별

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (Python) + Claude Code CLI (최종 판단) |
| **입력** | Phase 4까지의 전체 데이터 |
| **출력** | 최종 아이디어 목록 (등급 포함) |
| **성공 기준** | 1개 이상 S/A급 산출 (없으면 B급까지 포함) |
| **검증 방법** | 규칙 기반 — NUMR-V 점수 계산 정합성 + 24h 의미적 중복 체크 |
| **실패 처리** | 0개 산출 시 로그 기록, 대시보드에 "이 시간대 유효 아이디어 없음" 표시 |

**NUMR-V 스코어링 체계 (신규):**

```
NUMR-V = (N×0.10 + U×0.20 + M×0.20 + R×0.25 + V×0.25)

N(Novelty, 1~5):        기존 서비스 대비 차별화 정도
U(Urgency, 1~5):        문제의 긴급성/반복성
M(Market Demand, 1~5):   프록시 지표 기반 시장 수요 (유사 서비스 수, 검색량, 커뮤니티 규모)
R(Revenue, 1~5):         수익 모델 강도, ARPU 잠재력
V(Validation, 1~5):      시장 검증 결과 종합
  - 5: 경쟁사 약하고 수요 프록시 강하고 타이밍 완벽
  - 4: 경쟁사 있으나 차별화 가능 + 수요 중간 이상
  - 3: 경쟁 치열하나 니치 가능 또는 수요 소규모
  - 2: 경쟁 치열하고 차별화 불명확
  - 1: 레드오션 또는 시장 비존재

산출 프로세스 (상대+절대 하이브리드):
1. Claude가 배치 내 전체 가설을 비교하여 N, U, M, R 상대 순위 평가
2. V(Validation)는 Phase 4 시장 검증 점수에서 규칙 기반 산출
3. NUMR-V 가중합 계산 후 배치 내 상대 순위와 절대 하한선을 결합하여 등급 분류
```

**기존 NUMR 대비 변경:**
- M: Market Size → Market Demand 재정의 (TAM 수치 추정 → 프록시 지표 기반)
- R(수익성) 가중치: 0.35 → 0.25 (검증 축 추가로 재배분)
- V(Validation) 신설: 가중치 0.25 — 시장 검증이 스코어에 직접 반영
- N(신선도) 가중치: 0.15 → 0.10 (검증이 더 중요)

**등급 기준 (상대+절대 하이브리드):**

| 등급 | 조건 | 라벨 | 액션 |
|------|------|------|------|
| S | 배치 내 상위 10% **AND** NUMR-V ≥ 4.0 | Validated Cash Cow | Discord 즉시 알림 + 상세 리포트 |
| A | 배치 내 상위 30% **AND** NUMR-V ≥ 3.2 | High Potential | Discord 알림 + 대시보드 강조 |
| B | NUMR-V ≥ 2.5 | Moderate | 대시보드 기록 |
| C | NUMR-V ≥ 1.5 | Needs Pivot | 대시보드 기록 (하위 표시) |
| D | NUMR-V < 1.5 | Archive Only | 아카이브만 |

> S/A등급은 **상대 순위 + 절대 하한선**을 모두 충족해야 승격. B/C/D는 절대값만으로 분류 (배치 크기가 작을 때 안전장치).

#### Phase 6: 산출물 기록 & 알림

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (Python, Discord 웹훅) |
| **입력** | Phase 5 최종 아이디어 목록 |
| **출력** | 대시보드 배치, Discord 메시지, 리포트 파일 |
| **성공 기준** | 대시보드 파일 갱신 + (S급 존재 시) Discord 전송 성공 |
| **검증 방법** | 규칙 기반 — 파일 존재 확인, HTTP 200 응답 확인 |
| **실패 처리** | Discord 실패 시 자동 재시도 3회 → 보류 큐에 저장 (기존 패턴 유지) |

### 2.3 LLM 판단 영역 vs 코드 처리 영역

| Claude CLI가 수행 (Phase 2, 4, 5-NUMR) | Python 스크립트 직접 처리 (Phase 1, 3, 5-중복제거, 6) |
|----------------------------------------|-------------------------------------------------------|
| 외부 신호에서 기회 영역 식별 | Playwright 크롤링 실행 (Phase 1) |
| 역방향 서비스 가설 구상 | SQLite 카탈로그 검색/매칭 (Phase 3) |
| "이 서비스에 필요한 데이터" 추론 | 임베딩 기반 의미적 매칭 1차 필터 (Phase 3) |
| 경쟁사 분석 결과 해석/차별화 도출 | 필드간 join 가능성 분석 (Phase 3) |
| 시장 수요 프록시 분석 | NUMR-V 점수 계산 (Phase 5) |
| 서비스명/컨셉 문장 생성 | 임베딩 기반 24h 중복 선필터 (Phase 5) |
| 최종 품질 자기검증 (배치 내 상대 평가) | FastAPI 대시보드/Discord 발행 (Phase 6) |
| 수익 모델 다각도 제안 | 파일 I/O, 로그 기록, 타임아웃 관리 |

### 2.4 시간 예산 배분 (기본 + 가변 버킷)

```
총 60분 예산 (기본 36분 고정 + 가변 24분 공유 풀):

                          기본      가변(공유풀)    합계 범위
Phase 1: 맥락 수집        5분      0~5분          5~10분
Phase 2: 가설 생성       10분      0~5분         10~15분
Phase 3: API 매칭         5분      0~5분          5~10분
Phase 4: 시장 검증        8분      0~12분         8~20분 (적응형 깊이)
Phase 5: 스코어링         2분      0~3분          2~5분
Phase 6: 기록/알림        1분      0~1분          1~2분
버퍼:                     5분
───────────────────────────────────────────
기본 합계:               36분
가변 풀 총량:            24분 (전 Phase 공유 — 합계 60분을 초과할 수 없음)

※ 가변 풀 규칙: 각 Phase가 기본 시간을 초과할 경우 공유 풀에서 차감.
   남은 공유 풀이 0이면 이후 Phase는 기본 시간만 사용.
   run_engine.py가 매 Phase 시작 시 잔여 풀을 계산하여 할당.
```

**적응형 깊이 규칙 (Phase 4):**
- Phase 3 통과 가설 수에 따라 가변 버킷 배분:
  - 1~3개: 가설당 최대 5분 (심층 검증 — Playwright 2~3회 + Claude 분석)
  - 4~6개: 가설당 최대 3분 (표준 검증 — Playwright 1~2회 + Claude 분석)
  - 7개+: 가설당 최대 2분 (간소화 검증 — Playwright 1회 + Claude 분석)
- 남은 시간 < 10분: Phase 4를 간소화 모드로 전환 (Playwright 검색 1회 + Claude 자체 지식 기반 분석)
- 남은 시간 < 5분: Phase 4 스킵, Phase 5에서 V=중립(3) 부여

---

## 3. 구현 스펙

### 3.1 폴더 구조

```
/project-root
├── CLAUDE.md                           # 프로젝트 개요, 핵심 원칙, 금지 사항 (claude -p 기본 프롬프트)
├── /.claude
│   ├── /skills
│   │   ├── /signal-collector
│   │   │   ├── SKILL.md                # 외부 신호 수집 지침
│   │   │   ├── /scripts
│   │   │   │   ├── crawl_trends.py     # Google Trends 크롤링
│   │   │   │   ├── crawl_news.py       # 뉴스 크롤링
│   │   │   │   ├── crawl_tech.py       # ProductHunt/HN 크롤링
│   │   │   │   ├── crawl_policy.py     # 정책/법령 크롤링
│   │   │   │   ├── crawl_funding.py    # 펀딩/스타트업 크롤링
│   │   │   │   └── signal_aggregator.py # 신호 통합/캐싱
│   │   │   └── /references
│   │   │       └── source_config.json  # 소스별 URL/셀렉터 설정
│   │   │
│   │   ├── /catalog-manager
│   │   │   ├── SKILL.md                # 카탈로그 관리 지침
│   │   │   └── /scripts
│   │   │       ├── catalog_scanner.py  # data.go.kr 스캔 (증분/전수)
│   │   │       ├── catalog_store.py    # SQLite CRUD (기존 계승 + 확장)
│   │   │       ├── catalog_indexer.py  # 역방향 추론용 인덱스 + 임베딩 생성
│   │   │       └── refresh_scheduler.sh # 갱신 스케줄러 (주간 증분 + 월간 전수)
│   │   │
│   │   ├── /api-matcher
│   │   │   ├── SKILL.md                # API 매칭/검증 지침
│   │   │   └── /scripts
│   │   │       ├── semantic_matcher.py # 의미적 매칭 엔진 (임베딩 선필터 + Claude 정밀)
│   │   │       ├── join_analyzer.py    # 필드간 join 가능성 분석
│   │   │       ├── sample_validator.py # API 응답 샘플 검증
│   │   │       └── feasibility.py      # 구현 가능성 산출
│   │   │
│   │   ├── /market-validator
│   │   │   ├── SKILL.md                # 시장 검증 지침
│   │   │   └── /scripts
│   │   │       ├── competitor_search.py   # 경쟁사 검색 (Playwright)
│   │   │       ├── market_proxy_scorer.py # 시장 수요 프록시 평가
│   │   │       └── validation_scorer.py   # 시장 검증 점수 산출
│   │   │
│   │   ├── /scorer
│   │   │   ├── SKILL.md                # 스코어링 지침
│   │   │   └── /scripts
│   │   │       ├── numrv_scorer.py     # NUMR-V 스코어 계산
│   │   │       ├── dedup_engine.py     # 임베딩 기반 의미적 중복 제거
│   │   │       └── grade_classifier.py # 등급 분류 (상대+절대 하이브리드)
│   │   │
│   │   └── /publisher
│   │       ├── SKILL.md                # 산출물 발행 지침
│   │       └── /scripts
│   │           ├── dashboard_writer.py  # 대시보드 배치 기록
│   │           ├── discord_notifier.py  # Discord 웹훅 (리치 embed)
│   │           ├── report_generator.py  # 일간/주간 리포트
│   │           └── archive_manager.py   # 아카이브 관리
│   │
│   └── /prompts                        # Claude CLI 호출용 프롬프트 파일
│       ├── phase2_hypothesis.md        # Phase 2 전용 — 역방향 추론 지침, 카탈로그 참조 규칙, 출력 스키마
│       ├── phase4_validation.md        # Phase 4 전용 — 시장 검증 지침, 프록시 지표 평가 기준, 출력 스키마
│       └── phase5_scoring.md          # Phase 5 전용 — 배치 내 NUMR 상대 순위 평가 지침, 출력 스키마
│
├── /data                               # 데이터 저장소
│   ├── public_api_catalog.sqlite3      # API 카탈로그 DB (기존)
│   ├── ideas_archive.jsonl             # 아이디어 아카이브
│   ├── dashboard_batches.jsonl         # 대시보드 배치
│   ├── feedback.jsonl                  # 대시보드 피드백 (FastAPI가 쓰기, run_engine.py가 읽기)
│   ├── signal_cache.json               # 외부 신호 캐시
│   ├── skip_runs.jsonl                 # 스킵 로그
│   ├── webhook_config.json             # Discord 웹훅 설정
│   └── /embeddings                     # 임베딩 인덱스 (ko-sroberta)
│       ├── catalog_embeddings.npy      # API 카탈로그 임베딩 벡터
│       └── catalog_index.faiss         # FAISS 인덱스
│
├── /output                             # 실행별 중간/최종 산출물
│   ├── /signals                        # Phase 1 결과
│   ├── /hypotheses                     # Phase 2 결과
│   ├── /validations                    # Phase 4 결과
│   ├── /reports                        # 일간/주간 리포트
│   └── /logs                           # 구조화 JSON 로그 (일별)
│
├── /server                             # FastAPI 서버
│   ├── app.py                          # FastAPI 엔트리포인트 (uvicorn)
│   ├── /routers
│   │   ├── ideas.py                    # 아이디어 CRUD API
│   │   ├── feedback.py                 # 피드백 수신 API
│   │   └── health.py                   # 시스템 헬스 API
│   ├── /static
│   │   └── /dashboard                  # Vue 3 CDN 대시보드
│   │       ├── index.html
│   │       ├── app.js
│   │       └── style.css
│   └── /schemas
│       └── api_contracts.py            # Pydantic 모델 (API 입출력 스키마)
│
├── /scripts                            # 실행 스크립트
│   ├── run_engine.py                   # 메인 오케스트레이터 (Phase 1~6 순서 제어)
│   ├── run_engine.bat                  # Windows 실행 래퍼
│   ├── _loop_runner.py                 # 매시 정각 루프 (병렬 최대 2개)
│   └── scheduler_control.bat           # 작업 스케줄러 제어
│
├── /tests                              # 테스트
│   ├── test_matcher.py
│   ├── test_scorer.py
│   ├── test_workflow.py
│   └── test_dedup.py
│
└── /docs                               # 참고 문서
    ├── scoring_formula.md              # NUMR-V 스코어링 상세
    └── api_catalog_schema.md           # DB 스키마 문서
```

### 3.2 프롬프트 파일 구조

> **아키텍처 변경**: v6.0에서는 CLAUDE.md가 오케스트레이터가 아니다. `run_engine.py`(Python)가 전체 파이프라인을 제어하며, Claude CLI(`claude -p`)는 Phase 2, 4, 5에서 호출된다 (Phase 2: 가설 생성, Phase 4: 시장 검증, Phase 5: NUMR 상대 순위 평가). CLAUDE.md와 Phase별 프롬프트 파일은 이 호출 시 시스템 프롬프트 역할을 한다.

| 파일 | 역할 |
|------|------|
| **CLAUDE.md** | 프로젝트 개요, 핵심 원칙, 금지 사항. `claude -p` 호출 시 기본 시스템 프롬프트로 주입 |
| **`.claude/prompts/phase2_hypothesis.md`** | Phase 2 전용 프롬프트: 역방향 추론 지침, 카탈로그 참조 규칙, 출력 JSON 스키마 |
| **`.claude/prompts/phase4_validation.md`** | Phase 4 전용 프롬프트: 시장 검증 지침, 프록시 지표 평가 기준, 출력 JSON 스키마 |
| **`.claude/prompts/phase5_scoring.md`** | Phase 5 전용 프롬프트: 배치 내 NUMR 상대 순위 평가 지침, 비교 기준, 출력 JSON 스키마 |

**CLAUDE.md 핵심 섹션:**

| 섹션 | 역할 |
|------|------|
| **프로젝트 개요** | 엔진 목적, 버전, 핵심 원칙 |
| **프롬프트 파일 참조** | Phase 2, 4, 5 전용 프롬프트 파일 경로와 사용 규칙 |
| **스킬 참조 매트릭스** | 어떤 Phase에서 어떤 스킬 스크립트를 사용하는가 |
| **품질 게이트** | 각 Phase 통과 기준, 실패 시 처리 |
| **Claude CLI 호출 규칙** | Phase 2, 4, 5 한정 — 토큰 예산, 파일 기반 출력, 재시도 정책 |
| **출력 포맷** | JSON 스키마, 대시보드 배치 형식, Discord embed 형식 |
| **금지 사항** | 존재하지 않는 API 언급, 허수 시장 수치 생성, 동일 템플릿 반복 |

### 3.3 실행 구조

**Claude CLI 호출 분리 근거:**
- Phase 2(가설 생성)와 Phase 4(시장 검증)은 완전히 다른 도메인 지식이 필요
- 가설 생성: API 카탈로그 도메인 지식 + 서비스 기획 사고
- 시장 검증: 경쟁 분석 + 시장 조사 방법론
- 각각의 프롬프트가 길어져 별도 `claude -p` 호출로 컨텍스트 윈도우 최적화

```
┌──────────────────────────────────────────────────┐
│        run_engine.py (Python 오케스트레이터)        │
│                                                    │
│  매시 정각 트리거 → Phase 순서 제어                 │
│  Phase간 데이터 전달 (파일 기반)                    │
│  품질 게이트 통과/탈락 판단                         │
│  타임아웃/적응형 깊이 관리                          │
│  동시 실행 제어 (최대 2개 병렬)                     │
│                                                    │
│  Phase 1 ─── Python 직접 실행 (Playwright 크롤링)  │
│  Phase 2 ─── claude -p (phase2_hypothesis.md)      │
│  Phase 3 ─── Python 직접 실행 (SQLite + 임베딩)    │
│  Phase 4 ─── claude -p (phase4_validation.md)      │
│  Phase 5 ─── Python + claude -p (NUMR 상대평가 + 중복제거) │
│  Phase 6 ─── Python 직접 실행 (FastAPI 배치 + Discord)│
└──────────────────────────────────────────────────┘
```

**Claude CLI 호출 사양:**

| 호출 | 역할 | 트리거 | 입력 | 출력 | 프롬프트 |
|------|------|--------|------|------|----------|
| Phase 2 Claude 호출 | 외부 신호 + 카탈로그 기반 역방향 서비스 가설 생성 | `run_engine.py`가 Phase 1 완료 후 subprocess 호출 | `signals.json` + 카탈로그 도메인 요약 + 최근 24h 아카이브 + 피드백 요약 | `hypotheses.json` (후보 8~15개) | `.claude/prompts/phase2_hypothesis.md` |
| Phase 4 Claude 호출 | 가설별 시장 검증 수행 | `run_engine.py`가 Phase 3 완료 후 subprocess 호출 | Phase 3 통과 가설 목록 + Playwright 검색 결과 | `validations.json` (가설별 검증 리포트) | `.claude/prompts/phase4_validation.md` |
| Phase 5 Claude 호출 | 배치 내 NUMR 상대 순위 평가 | `run_engine.py`가 Phase 4 완료 후 subprocess 호출 | Phase 4 검증 완료 가설 전체 목록 | `numr_rankings.json` (가설별 N,U,M,R 점수) | `.claude/prompts/phase5_scoring.md` |

**데이터 전달:**
- 파일 기반: 모든 Phase 결과물은 `/output/{phase}/` 에 JSON으로 저장
- `run_engine.py`가 프롬프트에 파일 경로를 포함하여 `claude -p`에 전달
- Phase 2, 4, 5 Claude 호출 간 직접 연쇄 금지 — 반드시 `run_engine.py`를 통해 순차 실행

**파일 기반 LLM 출력 규칙:**
- **원자적 쓰기**: `.tmp` 확장자로 먼저 쓰고 완료 후 rename → 불완전 파일 방지
- **스키마 버전**: 모든 출력 JSON에 `"schema_version": "1.0"` 필드 포함
- **출력 방식**: Claude에게 지정된 파일 경로에 JSON을 직접 쓰도록 지시 (stdout 오염 방지)
- **재시도**: 파싱 실패 시 최대 2회 재호출 (프롬프트 변형). 3회 실패 시 해당 Phase 스킵 + 에스컬레이션 로그
- **검증**: 출력 파일 수신 후 Pydantic 스키마로 즉시 검증, 필수 필드 누락 시 재시도 트리거

### 3.4 스킬 파일 목록

| 스킬 | 역할 | 트리거 조건 | 주요 스크립트 |
|------|------|------------|-------------|
| `signal-collector` | 외부 신호 크롤링/캐싱 | `run_engine.py`가 Phase 1에서 호출 | `crawl_*.py`, `signal_aggregator.py` |
| `catalog-manager` | API 카탈로그 DB 관리, 도메인 요약 + 임베딩 생성, 주간/월간 갱신 | `run_engine.py`가 Phase 2 전 호출 + 갱신 스케줄러 | `catalog_scanner.py`, `catalog_indexer.py` |
| `api-matcher` | 필요 데이터 → 임베딩 선필터 + Claude 정밀 매칭, join 분석, 구현 가능성 | `run_engine.py`가 Phase 3에서 호출 | `semantic_matcher.py`, `join_analyzer.py`, `feasibility.py` |
| `market-validator` | 경쟁사 검색, 시장 수요 프록시 평가, 검증 점수 산출 | `run_engine.py`가 Phase 4에서 호출 | `competitor_search.py`, `market_proxy_scorer.py`, `validation_scorer.py` |
| `scorer` | NUMR-V 계산, 임베딩 기반 중복 제거, 등급 분류 (상대+절대 하이브리드) | `run_engine.py`가 Phase 5에서 호출 | `numrv_scorer.py`, `dedup_engine.py`, `grade_classifier.py` |
| `publisher` | FastAPI 배치 기록/Discord/리포트 발행 | `run_engine.py`가 Phase 6에서 호출 | `dashboard_writer.py`, `discord_notifier.py`, `report_generator.py` |

### 3.5 주요 산출물 파일 형식

**가설 JSON 스키마 (hypotheses.json):**
```json
{
  "schema_version": "1.0",
  "batch_id": "2026-02-18-14",
  "generated_at": "2026-02-18T14:05:00+09:00",
  "trigger_signals": ["외부 신호 요약"],
  "hypotheses": [
    {
      "id": "H001",
      "service_name": "...",
      "problem_statement": "...",
      "service_concept": "...",
      "target_buyer": "...",
      "target_user": "...",
      "service_type": "...",
      "revenue_model": "...",
      "required_data": ["데이터 니즈 1", "데이터 니즈 2"],
      "suggested_apis": ["API 제안 1", "API 제안 2"],
      "reasoning": "왜 이 서비스가 지금 필요한지 근거"
    }
  ]
}
```

**시장 검증 리포트 JSON:**
```json
{
  "schema_version": "1.0",
  "hypothesis_id": "H001",
  "validation": {
    "competitors": [
      {"name": "...", "url": "...", "differentiation": "..."}
    ],
    "market_proxies": {
      "similar_services_count": 3,
      "target_community_size": "약 50만 명 (관련 카페/커뮤니티 합산)",
      "search_trend": "상승",
      "proxy_basis": "네이버 카페 X 회원수 + Google Trends 12개월 추세"
    },
    "timing_score": 4,
    "timing_reason": "...",
    "monetization_cases": ["사례 1", "사례 2"],
    "mvp_weeks": 4,
    "mvp_complexity": "...",
    "validation_score": 78
  }
}
```

**대시보드 배치 (dashboard_batches.jsonl):**
```json
{
  "schema_version": "1.0",
  "batch_id": "2026-02-18-14",
  "timestamp": "...",
  "ideas": [
    {
      "id": "...",
      "service_name": "...",
      "grade": "S",
      "numrv_score": 4.35,
      "numrv_detail": {"N": 4, "U": 5, "M": 4, "R": 4, "V": 5},
      "batch_rank": 1,
      "batch_percentile": 95,
      "problem": "...",
      "concept": "...",
      "target": "...",
      "revenue_model": "...",
      "feasibility_pct": 78,
      "matched_apis": [...],
      "market_validation": {
        "competitors": [...],
        "market_proxies": {
          "similar_services_count": 2,
          "target_community_size": "...",
          "search_trend": "상승"
        },
        "timing": "...",
        "mvp_weeks": 4
      },
      "trigger_signal": "..."
    }
  ]
}
```

**Discord Embed 구조 (S급):**
```
💎 S급 아이디어 발견!
━━━━━━━━━━━━━━━━━━

📋 [서비스명]
NUMR-V: 4.65 (S) | 구현: 78% | MVP: 4주

🎯 문제
[구매자가 실제로 겪는 문제]

💡 솔루션
[어떤 API 데이터를 어떻게 결합해서 뭘 하는지]

📊 시장 검증
- 경쟁사: [경쟁사1] — 차별화: [포인트]
- 시장수요: [프록시 지표 요약] (근거: [커뮤니티 규모, 검색 추세 등])
- 타이밍: ⭐⭐⭐⭐ (정책 방향 부합)
- 수익모델: [모델] (유사사례: [사례])

🔧 API 구현
- [API1] → [데이터1]
- [API2] → [데이터2]
- join key: [공통키]

📅 트리거: [어떤 외부 신호가 이 아이디어를 촉발했는지]
```

**FastAPI 엔드포인트 계약:**

| 엔드포인트 | 메서드 | 요청 | 응답 | 용도 |
|-----------|--------|------|------|------|
| `/api/batches` | GET | `?date=&grade=` | `BatchListResponse` | 배치 목록 조회 |
| `/api/ideas/{id}` | GET | - | `IdeaDetailResponse` | 아이디어 상세 |
| `/api/feedback` | POST | `FeedbackRequest` (idea_id, action, comment) | `200 OK` | 피드백 수신 |
| `/api/health` | GET | - | `HealthResponse` | 시스템 상태/메트릭스 |
| `/static/dashboard/*` | GET | - | HTML/JS/CSS | 대시보드 정적 파일 서빙 |

> API 계약은 `/server/schemas/api_contracts.py`에 Pydantic 모델로 정의.

### 3.6 대시보드 설계

**기술 스택**: Vue 3 CDN (빌드 없는 SFC) + FastAPI 서빙
**서빙 방식**: FastAPI 서버가 정적 파일 + API 모두 제공 (`localhost:8000`)
**접근 범위**: 1차 localhost → 필요 시 LAN/Cloudflare Tunnel로 단계적 확장

**UI 구성:**
- **리스트 뷰**: 서비스명, 등급 뱃지, NUMR-V 점수, 배치 내 순위, 한줄 요약
- **단계별 아코디언** (클릭 시 섹션별 접힘/펼침):
  - 개요 (문제→솔루션→타깃)
  - 수익 분석 (수익모델→수익화 사례)
  - 시장 검증 (경쟁사→시장수요 프록시→타이밍)
  - 기술 구현 (API 매칭→join 경로→구현 가능성→MVP 추정)
- **필터/정렬**: 등급별, 도메인별, 날짜별, NUMR-V 점수순
- **검색**: 키워드 검색
- **통계 영역**: 일간/주간 S/A/B 분포, 도메인 분포
- **시스템 헬스**: 최근 실행 이력, Phase별 성공/실패, 연속 0개 경고
- **피드백**: 게시/보류/제외 버튼 + 코멘트 입력 → `POST /api/feedback`

**피드백 데이터 흐름:**
```
대시보드(Vue) → POST /api/feedback → data/feedback.jsonl → Phase 2 프롬프트에 요약 주입
```

### 3.7 카탈로그 갱신 (하이브리드)

```
1. 주간 증분 갱신 (매주 일요일 03:00 KST)
      │
      ▼
  catalog_scanner.py --mode incremental
      │ (마지막 스캔 이후 신규/변경 API만 처리)
      │ (last_scanned 타임스탬프 기반 필터링)
      ▼
  catalog_indexer.py --incremental
      │ (신규/변경분만 임베딩 재생성 + 도메인 요약 갱신)
      ▼
  완료 로그 기록

2. 월간 전수 스캔 (매월 첫째 일요일 03:00 KST)
      │
      ▼
  catalog_scanner.py --mode full --max-pages 1200
      │ (전수 스캔 + 폐지된 API 마킹)
      ▼
  catalog_indexer.py --full
      │ (전체 임베딩 인덱스 재생성)
      │ (카테고리별 도메인 요약 전체 갱신)
      ▼
  sample_validator.py --batch
      │ (신규/갱신 API 응답 샘플 검증)
      ▼
  완료 로그 기록
```

> ※ data.go.kr 변경 감지 API 존재 여부 확인 후, 가능하면 증분 갱신 고도화

### 3.8 피드백 루프 상세

**복합 접근 (3가지 메커니즘 병행):**

| 메커니즘 | 동작 | 저장 위치 |
|----------|------|----------|
| **블랙리스트** | 제외된 아이디어의 핵심 키워드/패턴을 목록화하여 Phase 2에서 유사 가설 생성 억제 | `data/feedback.jsonl` → 프롬프트 "회피 목록" |
| **선호도 학습** | 게시/보류 패턴을 분석하여 선호 도메인/서비스 유형 가중치 도출 | `data/feedback.jsonl` → 프롬프트 "선호 방향" |
| **코멘트 주입** | 최근 코멘트 상위 N개를 요약하여 Phase 2 프롬프트에 직접 삽입 | `data/feedback.jsonl` → 프롬프트 "사용자 코멘트 요약" |

**데이터 흐름:**
```
대시보드 → POST /api/feedback → data/feedback.jsonl
                                       │
                              run_engine.py Phase 2 준비 시 읽기
                                       │
                              피드백 요약을 구조화 블록으로 변환
                                       │
                              .claude/prompts/phase2_hypothesis.md 프롬프트 앞부분에 주입
```

### 3.9 로깅 & 모니터링

**파일 로그** (`output/logs/{YYYY-MM-DD}.jsonl`):
- 구조화 JSON — 각 이벤트가 한 줄의 JSON 오브젝트
- 기록 항목:
  - Phase 시작/종료/소요시간/성공여부
  - Claude CLI 호출 응답시간 및 출력 파일 크기
  - Playwright 크롤링 성공/실패/타임아웃 (URL별)
  - 품질 게이트 통과/탈락 상세 (가설 ID, 사유)
  - 임베딩 매칭 시간 및 후보 수

**대시보드 헬스 섹션** (`/api/health` + 대시보드 상단):
- 최근 N회 실행 이력 (성공/실패/스킵)
- Phase별 평균 소요시간 추세
- 일간/주간 성과 메트릭스: S/A급 비율, 평균 NUMR-V, 중복율
- 현재 실행 상태 (진행 중/대기/완료)

**Discord 이상 알림** (자동 트리거):
| 조건 | 알림 |
|------|------|
| 연속 3회 Phase 실패 | ⚠️ 시스템 경고 |
| 연속 6시간 0개 산출 | ⚠️ 품질 게이트 점검 필요 |
| Phase 타임아웃 초과 | ⚠️ 성능 저하 감지 |
| Claude CLI 호출 3회 연속 파싱 실패 | 🚨 에스컬레이션 필요 |

### 3.10 임베딩 인프라

| 항목 | 내용 |
|------|------|
| **모델** | ko-sroberta-multitask (한국어 특화 sentence-transformers) |
| **환경** | GPU 인퍼런스 |
| **인덱스 형식** | numpy 벡터 + FAISS 인덱스 (`data/embeddings/`) |
| **인덱싱 주기** | 카탈로그 갱신 시 재생성 (주간 증분 / 월간 전수) |
| **활용처** | Phase 3: API 카탈로그 의미적 매칭 1차 필터 (코사인 유사도 top-K) |
| | Phase 5: 24h 아카이브 대비 중복 탐지 선필터 (임계값 초과만 Claude에 전달) |
| **런타임 비용** | 사전 인덱싱으로 매시 인퍼런스는 쿼리 임베딩만 생성 (수 초) |

### 3.11 API 서버 설계

| 항목 | 내용 |
|------|------|
| **기술 스택** | FastAPI + uvicorn |
| **실행 방식** | `run_engine.py`와 독립 프로세스로 상시 실행 |
| **접근 범위** | 1차 `localhost:8000` → 필요 시 LAN/Cloudflare Tunnel로 단계적 확장 |
| **엔드포인트** | 3.5에 정의된 API 계약 참조 |
| **보안** | 1차: localhost 전용 (별도 인증 불요). 외부 공개 시 API 키 도입 |
| **정적 파일** | `/server/static/dashboard/` 아래 Vue CDN 대시보드 자동 서빙 |
| **데이터 소스** | `data/dashboard_batches.jsonl`, `data/feedback.jsonl`, `output/logs/` 직접 읽기 |

---

## 4. 리스크 & 완화 전략

| 리스크 | 영향도 | 완화 전략 |
|--------|--------|----------|
| Playwright 크롤링 차단/변경 | 높음 | 소스별 셀렉터를 `source_config.json`에 분리. 실패 시 graceful degradation — 해당 소스 스킵 |
| Claude Code CLI 응답 지연 | 중간 | Phase별 타임아웃 설정. 지연 시 후보 수 축소하여 시간 내 완료 |
| 1시간 내 미완료 | 중간 | 적응형 깊이 조절 — 시간 부족 시 Phase 4(시장 검증)를 간소화 모드로 전환 |
| API 카탈로그 데이터 노후화 | 낮음 | 주간 갱신 + `last_scanned` 필드로 오래된 데이터 마킹 |
| Discord embed 글자 제한 (4096자) | 낮음 | 요약형 카드 + "상세보기: 대시보드 링크" 구조 |
| 의미적 중복 미탐지 | 중간 | ko-sroberta 임베딩 선필터 + Claude가 임계값 초과분만 최종 대조 |
| Playwright 좀비 프로세스 | 중간 | `async with` 컨텍스트 매니저로 자동 정리 보장. 매 실행 시 잔여 Chromium 프로세스 체크 |
| LLM 출력 파싱 실패 | 중간 | 파일 기반 출력 + 원자적 쓰기(.tmp→rename) + Pydantic 검증 + 최대 2회 재시도 |
| 프롬프트 피로 (반복 패턴) | 중간 | 요일/시간대별 관점 변이 + 피드백 기반 자동 조정 + A/B 테스트 적응형 로테이션 |
| 연속 0개 산출 | 중간 | 복합 대응: 연속 N회 시 품질 게이트 점진적 완화 + Discord 경고 + 대시보드 상태 표시 |

---

## 5. 마이그레이션 전략

기존 v5.0에서 v6.0으로의 전환:

| 단계 | 작업 | 보존/재사용 | 새로 작성 |
|------|------|------------|----------|
| 1 | 폴더 구조 생성 | - | `/.claude/skills/`, `/.claude/prompts/`, `/server/`, `/data/embeddings/` 생성 |
| 2 | DB 마이그레이션 | `public_api_catalog.sqlite3` 데이터 | 인덱스 테이블, 도메인 요약 테이블 추가 |
| 3 | 임베딩 인프라 구축 | - | ko-sroberta 모델 설치, 초기 카탈로그 임베딩 생성 |
| 4 | 스킬 스크립트 작성 | `data_catalog_scanner.py` 핵심 로직 | signal-collector, api-matcher, market-validator (TAM→프록시) |
| 5 | 프롬프트 파일 작성 | - | CLAUDE.md(간결), `.claude/prompts/phase2_hypothesis.md`, `.claude/prompts/phase4_validation.md`, `.claude/prompts/phase5_scoring.md` |
| 6 | 스코어링 엔진 | NUMR 기본 구조 | V축 추가, M→Market Demand 재정의, 상대+절대 하이브리드 등급 |
| 7 | FastAPI 서버 + 대시보드 | - | `/server/` 전체 + Vue CDN 대시보드 완전 재작성 |
| 8 | Discord 알림 | 웹훅 인프라 | embed 포맷 강화 (프록시 지표 반영) + 이상 알림 추가 |
| 9 | 실행 스크립트 | `_loop_runner.py` 패턴 | `run_engine.py` (Python 오케스트레이터 + Claude CLI Phase 2,4 호출) |
| 10 | 테스트 + 로깅 | 테스트 패턴 | 새 스크립트별 테스트 + 구조화 JSON 로그 체계 |

---

## 6. MVP 전략

### 6.1 MVP 범위 (1차 구현 사이클)

| 포함 | 제외 (2차 이후) |
|------|----------------|
| Phase 2: 역방향 가설 생성 (코어) | Phase 4: 시장 검증 |
| Phase 3: API 매칭 + 임베딩 인프라 | FastAPI 서버 + 대시보드 |
| Phase 1 간소화: Google Trends만 | 나머지 외부 신호 소스 (뉴스/정책/펀딩) |
| 수동 신호 입력 지원 (CLI 인자) | Discord 알림 |
| JSON 파일 출력 | 피드백 루프 |
| 기본 로그 기록 | 대시보드 헬스/모니터링 |

### 6.2 MVP 검증 목표

- 역방향 추론이 v5.0의 정적 템플릿 반복 문제를 해결하는지 확인
- 임베딩 기반 의미적 매칭이 토큰 매칭 대비 유의미하게 나은지 확인
- Claude CLI 호출의 파일 기반 출력 + 파싱이 안정적인지 확인
- 1시간 내 Phase 1(간소화)+2+3 완료 가능한지 시간 예산 검증

---

## 7. 성공 지표

| 우선순위 | 지표 | 측정 방법 | 목표 |
|---------|------|----------|------|
| **1차** | 주당 S/A급 아이디어 산출 수 | 주간 리포트 자동 집계 | 주 5개+ (S급 1개+) |
| **2차** | 실제 MVP 전환율 | 게시 → 개발 착수 수동 추적 | 월 1건+ |
| 보조 | v5 대비 중복률 감소 | 24h 의미적 중복 탐지율 | 50%+ 감소 |
| 보조 | 도메인 다양성 | 주간 고유 도메인 수 | v5 대비 2배+ |
| 보조 | 시스템 안정성 | 매시 실행 성공률 | 95%+ |

---

## 8. QA 전략

### 8.1 자동 검증

| 대상 | 방법 | 실행 시점 |
|------|------|----------|
| LLM 출력 (Phase 2, 4, 5) | Pydantic 스키마 검증 — 필수 필드, 타입, 값 범위 | 매 출력 수신 시 |
| NUMR-V 점수 | 계산 정합성 체크 — 가중합 재계산, 등급 조건 부합 확인 | Phase 5 완료 시 |
| 중복 탐지 | 임베딩 유사도 + Claude 판단 교차 검증 | Phase 5 완료 시 |
| API 매칭 | 매칭된 API가 카탈로그에 실제 존재하는지 DB 조회 | Phase 3 완료 시 |

### 8.2 메트릭스 모니터링

- 일간/주간 추세 추적 (대시보드 헬스 섹션 연동):
  - S/A/B/C/D 등급 분포 변화
  - 평균 NUMR-V 점수 추이
  - Phase별 소요시간 추이
  - 품질 게이트 탈락률 추이
  - 중복 탐지 비율 추이
- 이상 감지 시 Discord 경고 (3.9 참조)

### 8.3 수동 검토

- 주 1회: 무작위 샘플 5개 아이디어를 수동 검토
  - 논리적 일관성 (문제→솔루션→타깃 연결이 자연스러운가)
  - API 매칭 적절성 (제안된 API가 실제로 필요한 데이터를 제공하는가)
  - 신선도 (최근 2주 내 유사 아이디어 없는가)
- 프롬프트 A/B 테스트 결과 주간 리뷰

---

## 부록 A: 기존 v5.0 참조 매핑

| v6.0 구성요소 | v5.0 대응 파일 | 참조 범위 |
|-------------|---------------|----------|
| `catalog-manager/scripts/catalog_scanner.py` | `data_catalog_scanner.py` | 스캔 로직 계승 |
| `catalog-manager/scripts/catalog_store.py` | `data_catalog_store.py` | DB 스키마 + CRUD 계승, 인덱스 확장 |
| `api-matcher/scripts/feasibility.py` | `catalog_feasibility.py` | 매칭 로직 참고, 의미적 매칭으로 대체 |
| `scorer/scripts/numrv_scorer.py` | `fnm_scorer.py` | NUMR 기본 구조 참고, V축 추가 |
| `publisher/scripts/discord_notifier.py` | `notifier.py` | 웹훅 전송 로직 계승, embed 강화 |
| `publisher/scripts/dashboard_writer.py` | `dashboard.html` + `main.py` | 완전 재작성 |
| `scripts/run_engine.py` | `main.py` + `workflow.py` | 오케스트레이션 패턴 참고, Python 오케스트레이터 + Claude CLI(Phase 2, 4, 5) 호출로 대체 |
| `scripts/_loop_runner.py` | `_loop_runner.py` | 정각 정렬/락 패턴 계승 |
| `market-validator/scripts/market_proxy_scorer.py` | *(신규)* | v5.0에 없던 시장수요 프록시 평가 — TAM 추정 대신 검증 가능한 프록시 지표 사용 |
| `.claude/prompts/phase2_hypothesis.md` | *(신규)* | Phase 2 Claude CLI 호출 전용 프롬프트 (역방향 추론 지침, 출력 JSON 스키마) |
| `.claude/prompts/phase4_validation.md` | *(신규)* | Phase 4 Claude CLI 호출 전용 프롬프트 (시장 검증 지침, 프록시 지표 평가 기준) |
| `.claude/prompts/phase5_scoring.md` | *(신규)* | Phase 5 Claude CLI 호출 전용 프롬프트 (배치 내 NUMR 상대 순위 평가 지침) |
| `server/app.py` | *(신규)* | FastAPI 서버 — 대시보드 서빙 + 피드백 API + 시스템 헬스 엔드포인트 |
| `data/embeddings/` | *(신규)* | ko-sroberta 기반 임베딩 인덱스 (카탈로그 의미적 매칭 + 중복 탐지) |
| `data/feedback.jsonl` | *(신규)* | 사용자 피드백 저장 — 블랙리스트/선호도/코멘트 → Phase 2 프롬프트 주입 |
