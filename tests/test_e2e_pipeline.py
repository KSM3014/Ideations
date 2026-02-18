"""2차 확장 테스트 — E2E 파이프라인 (retry, time pressure, feedback, empty signals)."""

import json
import sys
import time
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

from run_engine import IdeationEngine, TimeBudget


# ── 공통 테스트용 응답 ──

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
]


def _make_claude_side_effect():
    """기본 Phase별 Claude CLI 응답 side_effect."""
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
    """SemanticMatcher 목."""
    mock = MagicMock()
    mock.match_hypothesis.return_value = {
        "hypothesis_id": "H-001",
        "matches_by_need": [
            {"field_name": "실시간교통정보", "matched_apis": [{"api_id": "API-001", "score": 0.8}]},
        ],
        "unique_apis": [
            {"api_id": "API-001", "score": 0.8},
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


def _setup_engine(tmp_path, monkeypatch, manual_signals="AI 교통 트렌드"):
    """공통 엔진 설정 — 출력 경로 리다이렉트 + 외부 의존성 목."""
    monkeypatch.setattr("config.DASHBOARD_BATCHES_PATH", tmp_path / "batches.jsonl")
    monkeypatch.setattr("config.IDEAS_ARCHIVE_PATH", tmp_path / "archive.jsonl")
    monkeypatch.setattr("config.FEEDBACK_PATH", tmp_path / "feedback.jsonl")
    monkeypatch.setattr("config.WEBHOOK_CONFIG_PATH", tmp_path / "webhook.json")
    monkeypatch.setattr("config.LOG_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir(exist_ok=True)

    engine = IdeationEngine(manual_signals=manual_signals)

    # SemanticMatcher 목
    mock_matcher = _make_mock_matcher()
    monkeypatch.setattr("semantic_matcher.SemanticMatcher", lambda *a, **k: mock_matcher)

    # CompetitorSearcher 목
    mock_searcher = _make_mock_competitor_searcher()
    monkeypatch.setattr("competitor_search.CompetitorSearcher", lambda *a, **k: mock_searcher)

    return engine


class TestPhase2RetrySuccess:
    """Phase 2 파싱 실패 후 재시도 성공 시나리오."""

    def test_phase2_parse_failure_then_retry_success(self, tmp_path, monkeypatch):
        """첫 번째 _run_subprocess 호출이 파싱 불가 → 내부 재시도로 두 번째에서 성공."""
        engine = _setup_engine(tmp_path, monkeypatch)

        # ClaudeCLIInvoker 의 내부 재시도 로직을 활용하기 위해
        # _run_subprocess 를 목 처리 (invoke 가 아닌 저수준)
        # 재시도 대기 시간 제거
        engine.claude.wait_base = 0
        engine.claude.wait_max = 0

        subprocess_call_count = {"n": 0}

        def mock_run_subprocess(prompt):
            subprocess_call_count["n"] += 1
            if subprocess_call_count["n"] == 1:
                # 첫 호출: 파싱 불가능한 출력 → _extract_json 에서 ValueError
                return "this is not valid json"
            # 이후 호출: phase 구분 없이 valid JSON 반환
            # invoke 는 phase 를 _run_subprocess 에 전달하지 않으므로
            # 모든 phase 의 응답을 하나로 통일
            return json.dumps(PHASE2_RESPONSE)

        # _run_subprocess 를 패치하여 내부 retry 가 동작하도록 함
        original_run_subprocess = engine.claude._run_subprocess
        engine.claude._run_subprocess = mock_run_subprocess

        # 나머지 phase (4, 5) 에서는 invoke 를 직접 목으로 대체하면
        # _run_subprocess 패치와 충돌하므로, 모든 phase 를 _run_subprocess 로 처리
        # Phase 4, 5 도 valid JSON 을 반환해야 하므로 call_count 로 분기
        phase_call_tracker = {"phase2_done": False}

        def smart_subprocess(prompt):
            subprocess_call_count["n"] += 1
            if not phase_call_tracker["phase2_done"]:
                if subprocess_call_count["n"] == 1:
                    return "not valid json — triggers retry"
                phase_call_tracker["phase2_done"] = True
                return json.dumps(PHASE2_RESPONSE)
            # Phase 4, 5 등 후속 호출
            if "검증 대상" in prompt or "timing_fit" in prompt:
                return json.dumps(PHASE4_RESPONSE)
            if "평가 대상" in prompt or "N, U, M, R" in prompt:
                return json.dumps(PHASE5_RESPONSE)
            return json.dumps(PHASE2_RESPONSE)

        subprocess_call_count["n"] = 0
        engine.claude._run_subprocess = smart_subprocess

        result = engine.run()

        assert result["success"] is True
        assert len(result["phases"]["phase2"]["hypotheses"]) >= 1
        # 최소 2번 이상 _run_subprocess 호출 (첫 번째 실패 + 재시도 성공)
        assert subprocess_call_count["n"] >= 2


class TestTimePressureSimplified:
    """시간 압박 시 Phase 4 간소화."""

    def test_time_pressure_simplifies_phase4(self):
        """total_sec=600 (10분), 1초 경과 → remaining=599 < 600 → 'simplified'."""
        tb = TimeBudget(total_sec=600)

        # monotonic 을 패치하여 1초 경과 시뮬레이션
        # 이렇게 하면 remaining = 600 - 1 = 599 < PHASE4_SIMPLIFY_THRESHOLD_SEC(600)
        start = tb._started_at
        with patch("time.monotonic", return_value=start + 1):
            depth = tb.adaptive_depth(3)

        assert depth == "simplified"


class TestFeedbackBlacklistInjected:
    """피드백 블랙리스트가 Phase 2 프롬프트에 주입되는지 확인."""

    def test_feedback_blacklist_injected(self, tmp_path, monkeypatch):
        """feedback.jsonl 에 blacklist 피드백 기록 → Phase 2 프롬프트에 'blacklist' 포함."""
        # 피드백 파일 생성
        feedback_path = tmp_path / "feedback.jsonl"
        feedback_records = [
            {"hypothesis_id": "H-OLD-001", "action": "blacklist", "reason": "중복"},
            {"hypothesis_id": "H-OLD-002", "action": "like", "reason": "좋음"},
        ]
        with open(feedback_path, "w", encoding="utf-8") as f:
            for rec in feedback_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        monkeypatch.setattr("config.FEEDBACK_PATH", feedback_path)
        monkeypatch.setattr("config.DASHBOARD_BATCHES_PATH", tmp_path / "batches.jsonl")
        monkeypatch.setattr("config.IDEAS_ARCHIVE_PATH", tmp_path / "archive.jsonl")
        monkeypatch.setattr("config.WEBHOOK_CONFIG_PATH", tmp_path / "webhook.json")
        monkeypatch.setattr("config.LOG_DIR", tmp_path / "logs")
        (tmp_path / "logs").mkdir(exist_ok=True)

        engine = IdeationEngine(manual_signals="테스트 신호")

        # Claude CLI 목 — Phase 2 프롬프트 캡처
        captured_prompts = []

        def capture_side_effect(prompt, *, phase=None):
            captured_prompts.append({"prompt": prompt, "phase": phase})
            if phase == 2:
                return PHASE2_RESPONSE
            elif phase == 4:
                return PHASE4_RESPONSE
            elif phase == 5:
                return PHASE5_RESPONSE
            return {"result": "ok"}

        engine.claude.invoke = MagicMock(side_effect=capture_side_effect)

        # SemanticMatcher, CompetitorSearcher 목
        mock_matcher = _make_mock_matcher()
        monkeypatch.setattr("semantic_matcher.SemanticMatcher", lambda *a, **k: mock_matcher)
        mock_searcher = _make_mock_competitor_searcher()
        monkeypatch.setattr("competitor_search.CompetitorSearcher", lambda *a, **k: mock_searcher)

        # Phase 1 결과를 직접 전달하여 _phase2 호출
        phase1_result = {
            "batch_id": engine.batch_id,
            "signals": [{"source": "manual", "title": "테스트", "url": "", "snippet": "테스트"}],
            "duration_sec": 0.1,
        }
        engine.budget.start_phase(2)
        engine._phase2(phase1_result)

        # Phase 2 프롬프트에 "blacklist" 포함 확인
        phase2_prompts = [c["prompt"] for c in captured_prompts if c["phase"] == 2]
        assert len(phase2_prompts) >= 1
        assert "blacklist" in phase2_prompts[0].lower() or "blacklisted" in phase2_prompts[0].lower()


class TestEmptySignalsStillGenerates:
    """빈 신호로도 Phase 2가 호출되는지 확인."""

    def test_empty_signals_still_generates(self, tmp_path, monkeypatch):
        """수동 신호 없이 signal_aggregator가 빈 리스트 반환 → Phase 2 정상 호출."""
        engine = _setup_engine(tmp_path, monkeypatch, manual_signals=None)

        # signal_aggregator 목 — 빈 신호 반환
        async def mock_collect():
            return []

        monkeypatch.setattr("signal_aggregator.collect_signals", mock_collect)

        # Claude CLI 목
        phase2_called = {"called": False}

        def side_effect(prompt, *, phase=None):
            if phase == 2:
                phase2_called["called"] = True
                return PHASE2_RESPONSE
            elif phase == 4:
                return PHASE4_RESPONSE
            elif phase == 5:
                return PHASE5_RESPONSE
            return {"result": "ok"}

        engine.claude.invoke = MagicMock(side_effect=side_effect)

        result = engine.run()

        assert result["success"] is True
        assert phase2_called["called"] is True
        assert "phase2" in result["phases"]
