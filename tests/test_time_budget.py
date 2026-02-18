"""MVP 게이트 테스트 #3~5 — 시간 예산 공유 풀 계산, 적응형 깊이, Phase 4 스킵."""

import time
from unittest.mock import patch

import pytest

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.run_engine import TimeBudget
from config import (
    BASE_BUDGET_SEC,
    TOTAL_BUDGET_SEC,
    VARIABLE_POOL_SEC,
    PHASE4_SIMPLIFY_THRESHOLD_SEC,
    PHASE4_SKIP_THRESHOLD_SEC,
)


class TestTimeBudgetPool:
    """테스트 #3: 시간 예산 공유 풀 계산 — 60분 초과 불가."""

    def test_initial_pool(self):
        tb = TimeBudget()
        assert tb.variable_pool_remaining == VARIABLE_POOL_SEC
        assert tb.total_sec == TOTAL_BUDGET_SEC

    def test_total_never_exceeds_60min(self):
        """기본 합계(36분) + 가변 풀(24분) = 60분, 초과 불가."""
        base_total = sum(BASE_BUDGET_SEC.values())
        assert base_total + VARIABLE_POOL_SEC <= TOTAL_BUDGET_SEC

    def test_phase_budget_includes_variable(self):
        tb = TimeBudget()
        # Phase 4는 기본 8분 + 가변 최대 12분 = 20분
        budget = tb.phase_budget(4)
        assert budget >= BASE_BUDGET_SEC[4]

    def test_pool_deduction_on_overshoot(self):
        """Phase가 기본 시간을 초과하면 공유 풀에서 차감."""
        tb = TimeBudget()
        initial_pool = tb.variable_pool_remaining

        # Phase 1 시작, monotonic을 모킹하여 기본 시간(5분) + 2분 초과 시뮬레이션
        start_time = time.monotonic()
        with patch("time.monotonic", side_effect=[
            start_time,                       # start_phase → _phase_starts 기록
            start_time + 7 * 60,              # end_phase → elapsed 계산
            start_time + 7 * 60,              # remaining_sec 등 후속 호출
        ]):
            tb._started_at = start_time
            tb.start_phase(1)

        with patch("time.monotonic", return_value=start_time + 7 * 60):
            elapsed = tb.end_phase(1)

        assert elapsed == 7 * 60
        assert tb.variable_pool_remaining < initial_pool

    def test_pool_zero_stops_variable_allocation(self):
        """풀이 0이면 이후 Phase는 기본 시간만 사용."""
        tb = TimeBudget()
        tb.variable_pool_remaining = 0

        budget = tb.phase_budget(4)
        # remaining_sec 가 충분하면 기본 시간만
        assert budget <= BASE_BUDGET_SEC[4] or budget <= tb.remaining_sec


class TestAdaptiveDepth:
    """테스트 #4: 적응형 깊이 — 가설 수 → 깊이 레벨."""

    def test_deep_for_3_or_less(self):
        tb = TimeBudget()
        assert tb.adaptive_depth(1) == "deep"
        assert tb.adaptive_depth(3) == "deep"

    def test_standard_for_4_to_6(self):
        tb = TimeBudget()
        assert tb.adaptive_depth(4) == "standard"
        assert tb.adaptive_depth(5) == "standard"
        assert tb.adaptive_depth(6) == "standard"

    def test_light_for_7_plus(self):
        tb = TimeBudget()
        assert tb.adaptive_depth(7) == "light"
        assert tb.adaptive_depth(8) == "light"
        assert tb.adaptive_depth(20) == "light"

    def test_simplified_when_under_10min(self):
        """남은 시간 < 10분 → simplified."""
        tb = TimeBudget()
        start = time.monotonic()
        # 남은 시간 = 60분 - 52분 = 8분 (< 10분)
        with patch("time.monotonic", return_value=start + 52 * 60):
            tb._started_at = start
            assert tb.adaptive_depth(3) == "simplified"

    def test_skipped_when_under_5min(self):
        """테스트 #5: 남은 시간 < 5분 → Phase 4 스킵 + V=3."""
        tb = TimeBudget()
        start = time.monotonic()
        # 남은 시간 = 60분 - 57분 = 3분 (< 5분)
        with patch("time.monotonic", return_value=start + 57 * 60):
            tb._started_at = start
            assert tb.adaptive_depth(3) == "skipped"


class TestPhase4SkipInEngine:
    """Phase 4 스킵 시 V=3 부여 확인 (run_engine.py 골격)."""

    def test_phase4_skipped_returns_default_v(self):
        from scripts.run_engine import IdeationEngine

        engine = IdeationEngine()
        # 시간을 거의 다 소진시킨다
        start = time.monotonic()
        with patch("time.monotonic", return_value=start + 57 * 60):
            engine.budget._started_at = start
            result = engine._phase4({"passed_count": 3})

        assert result.get("skipped") is True
        assert result.get("default_v") == 3
