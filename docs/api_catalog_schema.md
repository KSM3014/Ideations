# API 카탈로그 DB 스키마

## 데이터베이스

- 파일: `data/public_api_catalog.sqlite3`
- 엔진: SQLite 3 (WAL 모드)
- PRAGMA: `journal_mode=WAL`, `foreign_keys=ON`

## 테이블

### catalog_metadata

스키마 버전, 마지막 스캔 시각 등 메타데이터 키-값 저장.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| key | TEXT PK | 메타데이터 키 |
| value | TEXT NOT NULL | 메타데이터 값 |

현재 사용 키:
- `schema_version`: "1.0"
- `last_scanned_at`: ISO 8601 타임스탬프

### apis

공공 API 메타데이터 (10,000+ 레코드).

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 내부 시퀀스 |
| api_id | TEXT UNIQUE NOT NULL | data.go.kr API 고유 ID |
| name | TEXT NOT NULL | API 이름 |
| description | TEXT | API 설명 |
| category | TEXT | 분류 카테고리 |
| provider | TEXT | 제공 기관 |
| endpoint_url | TEXT | 엔드포인트 URL |
| data_format | TEXT DEFAULT 'JSON' | 응답 포맷 |
| is_active | INTEGER DEFAULT 1 | 활성 여부 (1=활성, 0=폐지) |
| last_scanned_at | TEXT | 마지막 스캔 시각 (ISO 8601) |
| created_at | TEXT NOT NULL | 생성 시각 |
| updated_at | TEXT NOT NULL | 수정 시각 |

인덱스:
- `idx_apis_category` ON apis(category)
- `idx_apis_active` ON apis(is_active)

### api_parameters

API별 요청 파라미터 목록.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 내부 시퀀스 |
| api_id | TEXT NOT NULL FK→apis | API 참조 |
| param_name | TEXT NOT NULL | 파라미터 이름 |
| param_type | TEXT DEFAULT 'string' | 타입 (string, integer, date 등) |
| description | TEXT | 파라미터 설명 |
| required | INTEGER DEFAULT 0 | 필수 여부 (1=필수) |

제약: UNIQUE(api_id, param_name)
인덱스: `idx_api_params_api_id` ON api_parameters(api_id)

### api_operations

API별 오퍼레이션(엔드포인트) 목록.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 내부 시퀀스 |
| api_id | TEXT NOT NULL FK→apis | API 참조 |
| operation_name | TEXT NOT NULL | 오퍼레이션 이름 |
| http_method | TEXT DEFAULT 'GET' | HTTP 메서드 |
| path | TEXT | 경로 |
| description | TEXT | 오퍼레이션 설명 |

제약: UNIQUE(api_id, operation_name)
인덱스: `idx_api_ops_api_id` ON api_operations(api_id)

### domain_summary

카테고리별 도메인 요약 (Phase 2 프롬프트 주입용).

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 내부 시퀀스 |
| category | TEXT UNIQUE NOT NULL | 분류 카테고리 |
| api_count | INTEGER DEFAULT 0 | 해당 카테고리 API 수 |
| representative_keywords | TEXT | 대표 키워드 (쉼표 구분) |
| summary_text | TEXT | 도메인 요약 텍스트 |
| updated_at | TEXT NOT NULL | 갱신 시각 |

## 임베딩 파일

`data/embeddings/` 디렉토리:

| 파일 | 형식 | 설명 |
|------|------|------|
| `catalog_embeddings.npy` | NumPy ndarray | API 설명 임베딩 벡터 (ko-sroberta-multitask) |
| `catalog_index.faiss` | FAISS IndexFlatIP | 코사인 유사도 검색용 인덱스 |
| `id_map.json` | JSON | 인덱스 순서 → api_id 매핑 |

## 갱신 흐름

```
catalog_scanner.py (Playwright)
    → catalog_store.py (SQLite CRUD)
        → catalog_indexer.py (임베딩 생성 + FAISS 빌드)
```

- 주간 증분: 신규/변경 API만 처리
- 월간 전수: 전체 재스캔 + 폐지 API 마킹 + 임베딩 전체 재생성
