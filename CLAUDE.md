# API Ideation Engine v6.0

공공 데이터 API 기반 서비스 아이디어 자동 발굴 엔진.

## 핵심 원칙

1. **Python 오케스트레이터 + Claude CLI 하이브리드**: `run_engine.py`가 6-Phase 파이프라인을 순차 제어. Claude CLI(`claude -p`)는 Phase 2(가설 생성), Phase 4(시장 검증), Phase 5(NUMR 상대평가)에서만 호출.
2. **데이터 무결성**: 모든 JSON/JSONL 쓰기는 `.tmp` → `os.replace()` 원자적 패턴.
3. **시간 예산 60분**: 기본 36분(고정) + 가변 24분(공유 풀). 합계 60분 초과 불가.
4. **품질 게이트**: Phase 3 적합도 ≥ 40%, Phase 4 검증 ≥ 50점 미달 시 탈락.

## 금지 사항

- Claude CLI 호출 시 `codex exec` 사용 금지 (`claude -p` 전용)
- 카탈로그 전체를 프롬프트에 주입 금지 (도메인 요약만 사용)
- `data/webhook_config.json` 커밋 금지 (시크릿 포함)
- LLM으로 TAM 수치 추정 금지 (프록시 지표만 사용)

## 프로젝트 구조

- `config.py` — 전역 설정 (경로, 시간, 임계값)
- `logger.py` — 구조화 JSON 로그
- `utils.py` — 원자적 I/O, 배치 ID
- `scripts/run_engine.py` — 메인 오케스트레이터
- `server/` — FastAPI 대시보드
- `.claude/skills/` — Phase별 스킬 모듈
- `.claude/prompts/` — Claude CLI 프롬프트 템플릿
- `data/` — SQLite DB, 임베딩, JSONL
- `output/` — 실행별 산출물
- `tests/` — pytest 테스트 스위트
