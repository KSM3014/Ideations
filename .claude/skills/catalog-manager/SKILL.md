# Catalog Manager

API 카탈로그 DB 관리 스킬.

## 역할

data.go.kr 공공 API 메타데이터를 SQLite에 수집·갱신하고, 역방향 추론용 도메인 요약 + ko-sroberta 임베딩 인덱스를 생성한다.

## 스크립트

| 파일 | 역할 |
|------|------|
| `catalog_scanner.py` | data.go.kr Playwright 크롤러 (증분/전수 스캔) |
| `catalog_store.py` | SQLite CRUD (apis, api_parameters, api_operations, domain_summary) |
| `catalog_indexer.py` | ko-sroberta 임베딩 생성 + FAISS 인덱스 빌드 |
| `sample_validator.py` | API 응답 샘플 데이터 검증 |

## 호출자

- `run_engine.py` Phase 2 준비 시 `CatalogStore.get_domain_summaries()` 호출
- `scripts/catalog_refresh.py` — 주간/월간 갱신 배치

## DB 스키마

- `apis`: API 메타데이터 (api_id, name, category, description, ...)
- `api_parameters`: API 파라미터 목록
- `api_operations`: API 오퍼레이션 목록
- `domain_summary`: 카테고리별 도메인 요약 (Phase 2 프롬프트용)
- `catalog_metadata`: 스키마 버전, 마지막 스캔 시각

## 갱신 주기

- 주간 증분: 매주 일요일 03:00 KST (last_scanned 이후 변경분)
- 월간 전수: 매월 첫째 일요일 03:00 KST (전체 재스캔 + 임베딩 재생성)
