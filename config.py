"""전역 설정 — 경로, 시간 예산, 임계값, Claude CLI 설정, 재시도/백오프 표준."""

from __future__ import annotations

import os
from pathlib import Path

# ──────────────────────────── 경로 ────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = OUTPUT_DIR / "logs"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
PROMPTS_DIR = PROJECT_ROOT / ".claude" / "prompts"

CATALOG_DB_PATH = DATA_DIR / "public_api_catalog.sqlite3"
IDEAS_ARCHIVE_PATH = DATA_DIR / "ideas_archive.jsonl"
DASHBOARD_BATCHES_PATH = DATA_DIR / "dashboard_batches.jsonl"
FEEDBACK_PATH = DATA_DIR / "feedback.jsonl"
SIGNAL_CACHE_PATH = DATA_DIR / "signal_cache.json"
SKIP_RUNS_PATH = DATA_DIR / "skip_runs.jsonl"
WEBHOOK_CONFIG_PATH = DATA_DIR / "webhook_config.json"

CATALOG_EMBEDDINGS_PATH = EMBEDDINGS_DIR / "catalog_embeddings.npy"
CATALOG_INDEX_PATH = EMBEDDINGS_DIR / "catalog_index.faiss"
CATALOG_ID_MAP_PATH = EMBEDDINGS_DIR / "id_map.json"

# ──────────────────────────── 시간 예산 (초 단위) ────────────────────────────
TOTAL_BUDGET_SEC = 60 * 60  # 60분

# 기본 시간(고정)
BASE_BUDGET_SEC = {
    1: 5 * 60,   # Phase 1: 맥락 수집
    2: 10 * 60,  # Phase 2: 가설 생성
    3: 5 * 60,   # Phase 3: API 매칭
    4: 8 * 60,   # Phase 4: 시장 검증
    5: 2 * 60,   # Phase 5: 스코어링
    6: 1 * 60,   # Phase 6: 기록/알림
}
BUFFER_SEC = 5 * 60  # 버퍼

# 가변 풀(공유) — 합계 60분을 초과할 수 없음
VARIABLE_POOL_SEC = 24 * 60  # 24분

# Phase별 가변 최대치
VARIABLE_MAX_SEC = {
    1: 5 * 60,
    2: 5 * 60,
    3: 5 * 60,
    4: 12 * 60,
    5: 3 * 60,
    6: 1 * 60,
}

# ──────────────────────────── 적응형 깊이 (Phase 4) ────────────────────────────
ADAPTIVE_DEPTH = {
    "deep": {"max_hypotheses": 3, "per_hypothesis_sec": 5 * 60},
    "standard": {"max_hypotheses": 6, "per_hypothesis_sec": 3 * 60},
    "light": {"max_hypotheses": 999, "per_hypothesis_sec": 2 * 60},
}
PHASE4_SIMPLIFY_THRESHOLD_SEC = 10 * 60  # 남은 시간 <10분 → 간소화
PHASE4_SKIP_THRESHOLD_SEC = 5 * 60       # 남은 시간 <5분 → 스킵, V=3

# ──────────────────────────── 품질 게이트 임계값 ────────────────────────────
FEASIBILITY_PASS_THRESHOLD = 0.40   # Phase 3: 적합도 ≥ 40%
VALIDATION_PASS_THRESHOLD = 50      # Phase 4: 검증 점수 ≥ 50
DEDUP_SIMILARITY_THRESHOLD = 0.85   # Phase 5: 24h 중복 유사도

# ──────────────────────────── NUMR-V 가중치 ────────────────────────────
NUMRV_WEIGHTS = {
    "N": 0.10,  # Novelty
    "U": 0.20,  # Utility
    "M": 0.20,  # Market
    "R": 0.25,  # Realizability
    "V": 0.25,  # Validation
}

# 등급 절대 하한
GRADE_ABSOLUTE = {
    "S": 4.0,
    "A": 3.2,
    "B": 2.5,
    "C": 1.5,
}

# 등급 상대 백분위 (상위 N%)
GRADE_PERCENTILE = {
    "S": 10,
    "A": 30,
    "B": 60,
    "C": 85,
}

# ──────────────────────────── Claude CLI ────────────────────────────
CLAUDE_CLI_CMD = "claude"
CLAUDE_CLI_TIMEOUT_SEC = 600  # 10분

# ──────────────────────────── 재시도/백오프 표준 (tenacity) ────────────────────────────
RETRY_CLAUDE_CLI = {
    "max_retries": 2,
    "wait_base": 2,
    "wait_max": 30,
}
RETRY_DISCORD_WEBHOOK = {
    "max_retries": 3,
    "wait_base": 1,
    "wait_max": 10,
}
RETRY_PLAYWRIGHT = {
    "max_retries": 1,
    "wait_fixed": 5,
}

# ──────────────────────────── SLI/SLO ────────────────────────────
SLO = {
    "hourly_success_rate": 0.95,      # 매시 실행 성공률 ≥ 95%
    "phase_timeout_compliance": 0.98,  # Phase별 타임아웃 준수율 ≥ 98%
    "claude_cli_success_rate": 0.90,   # Claude CLI 응답 성공률 ≥ 90%
    "weekly_sa_output": 5,             # S/A급 주간 산출 ≥ 5개
}

ALERT_THRESHOLDS = {
    "hourly_success_24h_min": 0.90,    # 24h 내 성공률 < 90% → 경고
    "phase_timeout_consecutive": 3,     # 연속 3회 초과 → 경고
    "claude_parse_fail_consecutive": 5, # 연속 5회 파싱 실패 → 경고
    "weekly_sa_miss_consecutive": 2,    # 2주 연속 미달 → 경고
}

# ──────────────────────────── 신호 수집 ────────────────────────────
SIGNAL_ROTATION_ALWAYS = ["google_trends"]
SIGNAL_ROTATION_POOL = ["news", "tech", "policy", "funding"]
SIGNAL_ROTATION_PICK = 2  # 라운드로빈에서 2개 선택
SIGNAL_URL_CACHE_TTL_HOURS = 24
SIGNAL_SOURCE_TIMEOUT_SEC = 3 * 60  # 소스별 3분

# ──────────────────────────── 임베딩 ────────────────────────────
EMBEDDING_MODEL_NAME = "jhgan/ko-sroberta-multitask"
EMBEDDING_TOP_K = 20

# ──────────────────────────── DB ────────────────────────────
SCHEMA_VERSION = "1.0"
