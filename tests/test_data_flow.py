"""2차 확장 테스트 — Phase 간 데이터 흐름 검증 (IdeationEngine)."""

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 스킬 스크립트 경로 등록
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

from scripts.run_engine import IdeationEngine


def _make_mock_matcher():
    """SemanticMatcher 목을 생성한다."""
    mock = MagicMock()
    mock.match_hypothesis.return_value = {
        "hypothesis_id": "H-001",
        "matches_by_need": [
            {
                "field_name": "교통량",
                "matched_apis": [
                    {"api_id": "API-001", "score": 0.85, "rank": 1},
                    {"api_id": "API-002", "score": 0.75, "rank": 2},
                ],
            }
        ],
        "unique_apis": [
            {"api_id": "API-001", "score": 0.85, "rank": 1},
            {"api_id": "API-002", "score": 0.75, "rank": 2},
        ],
    }
    return mock


def _make_mock_searcher():
    """CompetitorSearcher 목을 생성한다."""
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[
        {"name": "서비스A", "url": "https://a.com", "snippet": "설명A"},
    ])
    return mock


def _build_engine_with_mocks(monkeypatch, tmp_path, phase2_responses=None):
    """공통 목 설정이 적용된 IdeationEngine을 생성한다."""
    # config 경로 패치
    monkeypatch.setattr("config.DASHBOARD_BATCHES_PATH", tmp_path / "batches.jsonl")
    monkeypatch.setattr("config.IDEAS_ARCHIVE_PATH", tmp_path / "archive.jsonl")
    monkeypatch.setattr("config.FEEDBACK_PATH", tmp_path / "feedback.jsonl")
    monkeypatch.setattr("config.WEBHOOK_CONFIG_PATH", tmp_path / "webhook_config.json")

    # SemanticMatcher 목
    mock_matcher = _make_mock_matcher()
    monkeypatch.setattr("semantic_matcher.SemanticMatcher", lambda *a, **k: mock_matcher)

    # CompetitorSearcher 목
    mock_searcher = _make_mock_searcher()
    monkeypatch.setattr("competitor_search.CompetitorSearcher", lambda *a, **k: mock_searcher)

    engine = IdeationEngine(manual_signals="테스트 신호")

    # Claude CLI 목 — Phase별 응답
    if phase2_responses is None:
        phase2_responses = [
            # Phase 2 응답: 가설 생성
            {
                "hypotheses": [
                    {
                        "id": "H-001",
                        "service_name": "스마트 교통 알리미",
                        "problem": "실시간 교통 정보 접근성 부족",
                        "solution": "공공 교통 API 기반 대시보드",
                        "target_buyer": "지자체 교통과",
                        "revenue_model": "SaaS 구독",
                        "opportunity_area": "스마트시티",
                        "data_needs": [
                            {
                                "field_name": "교통량",
                                "description": "시간대별 교통량",
                                "priority": "필수",
                            }
                        ],
                        "api_suggestions": [
                            {"api_name": "실시간 교통량 API", "reason": "실시간 교통량 데이터 제공"}
                        ],
                    }
                ]
            },
            # Phase 4 응답: 검증 결과
            {"timing_fit": 0.7, "revenue_reference": 0.6, "mvp_difficulty": 0.5},
            # Phase 5 응답: NUMR 스코어링
            [{"id": "H-001", "N": 4, "U": 4, "M": 3, "R": 4}],
        ]

    call_idx = {"n": 0}

    def mock_invoke(prompt, *, phase=None):
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(phase2_responses):
            return phase2_responses[idx]
        return phase2_responses[-1]

    engine.claude.invoke = MagicMock(side_effect=mock_invoke)

    return engine


class TestPhase1OutputFeedsPhase2:
    def test_phase1_output_feeds_phase2(self, monkeypatch, tmp_path):
        """Phase 1 출력에 signals 키가 있고 Phase 2가 소비할 수 있어야 한다."""
        engine = _build_engine_with_mocks(monkeypatch, tmp_path)
        p1 = engine._phase1()
        assert "signals" in p1
        assert isinstance(p1["signals"], list)
        # Phase 2가 이 출력을 소비할 수 있는지 검증
        p2 = engine._phase2(p1)
        assert "hypotheses" in p2


class TestPhase2OutputFeedsPhase3:
    def test_phase2_output_feeds_phase3(self, monkeypatch, tmp_path):
        """Phase 2 출력에 hypotheses 키가 있어야 한다."""
        engine = _build_engine_with_mocks(monkeypatch, tmp_path)
        p1 = engine._phase1()
        p2 = engine._phase2(p1)
        assert "hypotheses" in p2
        assert isinstance(p2["hypotheses"], list)
        assert len(p2["hypotheses"]) > 0


class TestPhase3OutputFeedsPhase4:
    def test_phase3_output_feeds_phase4(self, monkeypatch, tmp_path):
        """Phase 3 출력에 passed_hypotheses와 passed_count가 있어야 한다."""
        engine = _build_engine_with_mocks(monkeypatch, tmp_path)
        p1 = engine._phase1()
        p2 = engine._phase2(p1)
        p3 = engine._phase3(p2)
        assert "passed_hypotheses" in p3
        assert "passed_count" in p3
        assert isinstance(p3["passed_hypotheses"], list)


class TestPhase4OutputFeedsPhase5:
    def test_phase4_output_feeds_phase5(self, monkeypatch, tmp_path):
        """Phase 4 출력에 validations가 있어야 한다."""
        engine = _build_engine_with_mocks(monkeypatch, tmp_path)
        p1 = engine._phase1()
        p2 = engine._phase2(p1)
        p3 = engine._phase3(p2)
        p4 = engine._phase4(p3)
        assert "validations" in p4
        assert isinstance(p4["validations"], list)


class TestPhase5OutputFeedsPhase6:
    def test_phase5_output_feeds_phase6(self, monkeypatch, tmp_path):
        """Phase 5 출력에 scored_ideas가 있어야 한다."""
        engine = _build_engine_with_mocks(monkeypatch, tmp_path)
        p1 = engine._phase1()
        p2 = engine._phase2(p1)
        p3 = engine._phase3(p2)
        p4 = engine._phase4(p3)
        p5 = engine._phase5(p4)
        assert "scored_ideas" in p5
        assert isinstance(p5["scored_ideas"], list)


class TestFeedbackInjectedIntoPhase2Prompt:
    def test_feedback_injected_into_phase2_prompt(self, monkeypatch, tmp_path):
        """피드백 blacklist 항목이 Phase 2 프롬프트에 포함되어야 한다."""
        # 피드백 파일에 blacklist 기록
        feedback_path = tmp_path / "feedback.jsonl"
        feedback_records = [
            json.dumps({"hypothesis_id": "H-OLD-001", "action": "blacklist"}, ensure_ascii=False),
            json.dumps({"hypothesis_id": "H-OLD-002", "action": "like"}, ensure_ascii=False),
        ]
        feedback_path.write_text("\n".join(feedback_records) + "\n", encoding="utf-8")

        monkeypatch.setattr("config.FEEDBACK_PATH", feedback_path)
        monkeypatch.setattr("config.DASHBOARD_BATCHES_PATH", tmp_path / "batches.jsonl")
        monkeypatch.setattr("config.IDEAS_ARCHIVE_PATH", tmp_path / "archive.jsonl")
        monkeypatch.setattr("config.WEBHOOK_CONFIG_PATH", tmp_path / "webhook_config.json")

        engine = IdeationEngine(manual_signals="테스트 신호")

        captured_prompts = []

        def mock_invoke(prompt, *, phase=None):
            captured_prompts.append(prompt)
            return {
                "hypotheses": [
                    {
                        "id": "H-001",
                        "service_name": "테스트 서비스",
                        "problem": "테스트 문제",
                        "solution": "테스트 솔루션",
                        "target_buyer": "테스트 타깃",
                        "revenue_model": "SaaS",
                        "data_needs": [],
                    }
                ]
            }

        engine.claude.invoke = MagicMock(side_effect=mock_invoke)

        p1 = engine._phase1()
        engine._phase2(p1)

        # Phase 2 프롬프트에 blacklist가 포함되어 있는지 확인
        assert len(captured_prompts) >= 1
        phase2_prompt = captured_prompts[0]
        assert "blacklist" in phase2_prompt.lower() or "H-OLD-001" in phase2_prompt
