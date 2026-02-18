"""MVP Gate 테스트 — 전체 파이프라인 E2E (외부 의존성 목)."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SCRIPTS = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# 스킬 스크립트 경로
_SKILL_PATHS = [
    _PROJECT_ROOT / ".claude" / "skills" / "signal-collector" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "api-matcher" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "market-validator" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "scorer" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "publisher" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "catalog-manager" / "scripts",
]
for p in _SKILL_PATHS:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from run_engine import IdeationEngine


# ── 테스트용 고정 Claude CLI 응답 ──

PHASE2_RESPONSE = {
    "schema_version": "1.0",
    "hypotheses": [
        {
            "id": "H-001",
            "service_name": "스마트 교통 알리미",
            "problem": "실시간 교통 정보 부족",
            "solution": "공공 교통 API 대시보드",
            "target_buyer": "지자체",
            "revenue_model": "SaaS",
            "opportunity_area": "교통",
            "data_needs": [
                {"field_name": "실시간교통정보", "description": "도로별 실시간 교통량", "priority": "필수"},
                {"field_name": "버스위치정보", "description": "노선별 버스 위치", "priority": "필수"},
            ],
            "api_suggestions": [],
        },
        {
            "id": "H-002",
            "service_name": "날씨 농업 도우미",
            "problem": "기상 정보 활용 어려움",
            "solution": "기상 API 농업 알림",
            "target_buyer": "농가",
            "revenue_model": "구독",
            "opportunity_area": "농업",
            "data_needs": [
                {"field_name": "기상관측", "description": "시간별 기상 데이터", "priority": "필수"},
            ],
            "api_suggestions": [],
        },
    ],
}

PHASE4_RESPONSE = {
    "timing_fit": 0.7,
    "revenue_reference": 0.6,
    "mvp_difficulty": 0.8,
}

PHASE5_RESPONSE = [
    {"id": "H-001", "N": 4, "U": 4, "M": 3, "R": 4},
    {"id": "H-002", "N": 3, "U": 3, "M": 3, "R": 3},
]


def _make_claude_side_effect():
    """Phase별 Claude CLI 응답을 반환하는 side_effect 함수."""

    def side_effect(prompt, *, phase=None):
        if phase == 2:
            return PHASE2_RESPONSE
        elif phase == 4:
            return PHASE4_RESPONSE
        elif phase == 5:
            return PHASE5_RESPONSE
        return {"result": "ok"}

    return side_effect


def _make_mock_matcher():
    """SemanticMatcher 목 — 매칭 결과 반환."""
    mock = MagicMock()
    mock.match_hypothesis.return_value = {
        "hypothesis_id": "H-001",
        "matches_by_need": [
            {"field_name": "실시간교통정보", "matched_apis": [{"api_id": "API-001", "score": 0.8}]},
            {"field_name": "버스위치정보", "matched_apis": [{"api_id": "API-002", "score": 0.7}]},
        ],
        "unique_apis": [
            {"api_id": "API-001", "score": 0.8},
            {"api_id": "API-002", "score": 0.7},
        ],
    }
    return mock


def _make_mock_competitor_searcher():
    """CompetitorSearcher 목."""
    mock = MagicMock()

    async def mock_search(query):
        return [{"name": "경쟁사A", "url": "https://a.com", "snippet": "유사 서비스"}]

    mock.search = mock_search
    return mock


@pytest.fixture
def mock_engine(tmp_path, monkeypatch):
    """외부 의존성을 모두 목 처리한 IdeationEngine."""
    # 출력 경로를 tmp로 변경
    monkeypatch.setattr("config.DASHBOARD_BATCHES_PATH", tmp_path / "batches.jsonl")
    monkeypatch.setattr("config.IDEAS_ARCHIVE_PATH", tmp_path / "archive.jsonl")
    monkeypatch.setattr("config.FEEDBACK_PATH", tmp_path / "feedback.jsonl")
    monkeypatch.setattr("config.WEBHOOK_CONFIG_PATH", tmp_path / "webhook.json")
    monkeypatch.setattr("config.LOG_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir(exist_ok=True)

    engine = IdeationEngine(manual_signals="AI 교통 트렌드")

    # Claude CLI 목
    engine.claude.invoke = MagicMock(side_effect=_make_claude_side_effect())

    # SemanticMatcher 목 — semantic_matcher 모듈 패치
    mock_matcher = _make_mock_matcher()
    monkeypatch.setattr("semantic_matcher.SemanticMatcher", lambda *a, **k: mock_matcher)

    # CompetitorSearcher 목
    mock_searcher = _make_mock_competitor_searcher()
    monkeypatch.setattr("competitor_search.CompetitorSearcher", lambda *a, **k: mock_searcher)

    return engine


class TestE2EHappyPath:
    """MVP Gate #13: E2E Happy path — 목 기반 6-Phase 완주."""

    def test_full_pipeline_completes(self, mock_engine):
        result = mock_engine.run()

        assert result["success"] is True
        assert result["error"] is None
        assert result["batch_id"]
        assert "phase1" in result["phases"]
        assert "phase2" in result["phases"]
        assert "phase3" in result["phases"]
        assert "phase4" in result["phases"]
        assert "phase5" in result["phases"]
        assert "phase6" in result["phases"]

    def test_phase1_manual_signals(self, mock_engine):
        result = mock_engine.run()
        p1 = result["phases"]["phase1"]
        assert len(p1["signals"]) == 1
        assert p1["signals"][0]["source"] == "manual"

    def test_phase2_generates_hypotheses(self, mock_engine):
        result = mock_engine.run()
        p2 = result["phases"]["phase2"]
        assert len(p2["hypotheses"]) == 2
        assert p2["hypotheses"][0]["id"] == "H-001"

    def test_phase3_applies_feasibility_gate(self, mock_engine):
        result = mock_engine.run()
        p3 = result["phases"]["phase3"]
        assert p3["passed_count"] >= 0
        assert len(p3["matches"]) == 2

    def test_phase6_publishes(self, mock_engine):
        result = mock_engine.run()
        p6 = result["phases"]["phase6"]
        publish = p6["publish"]
        assert publish["dashboard_written"] is True
        assert publish["ideas_archived"] >= 0

    def test_total_duration_positive(self, mock_engine):
        result = mock_engine.run()
        assert result["total_duration_sec"] > 0


class TestPhase3AllFail:
    """MVP Gate #9: Phase 3 전체 탈락 → 0개 산출 정상 종료."""

    def test_zero_passed_continues(self, tmp_path, monkeypatch):
        monkeypatch.setattr("config.DASHBOARD_BATCHES_PATH", tmp_path / "batches.jsonl")
        monkeypatch.setattr("config.IDEAS_ARCHIVE_PATH", tmp_path / "archive.jsonl")
        monkeypatch.setattr("config.FEEDBACK_PATH", tmp_path / "feedback.jsonl")
        monkeypatch.setattr("config.WEBHOOK_CONFIG_PATH", tmp_path / "webhook.json")
        monkeypatch.setattr("config.LOG_DIR", tmp_path / "logs")
        (tmp_path / "logs").mkdir(exist_ok=True)

        engine = IdeationEngine(manual_signals="테스트")

        # Phase 2: 가설은 생성되나 data_needs가 없어서 매칭 불가
        def claude_side_effect(prompt, *, phase=None):
            if phase == 2:
                return {
                    "hypotheses": [
                        {
                            "id": "H-001",
                            "service_name": "테스트",
                            "problem": "없음",
                            "solution": "없음",
                            "target_buyer": "없음",
                            "revenue_model": "없음",
                            "data_needs": [],
                        }
                    ]
                }
            elif phase == 5:
                return []
            return {"timing_fit": 0.5, "revenue_reference": 0.5, "mvp_difficulty": 0.5}

        engine.claude.invoke = MagicMock(side_effect=claude_side_effect)

        # SemanticMatcher 목 — 빈 결과
        mock_matcher = MagicMock()
        mock_matcher.match_hypothesis.return_value = {
            "hypothesis_id": "H-001",
            "matches_by_need": [],
            "unique_apis": [],
        }
        monkeypatch.setattr("semantic_matcher.SemanticMatcher", lambda *a, **k: mock_matcher)

        result = engine.run()

        assert result["success"] is True
        assert result["phases"]["phase3"]["passed_count"] == 0
        # Phase 4~6은 빈 입력으로 정상 종료
        assert result["phases"]["phase6"]["publish"]["total_ideas"] == 0
