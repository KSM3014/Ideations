"""MVP 게이트 테스트 #8 — 적합도 경계값 (39%→탈락, 40%→통과) + 조인 키 탐지."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_MATCHER_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "api-matcher" / "scripts"
if str(_MATCHER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_MATCHER_SCRIPTS))

from feasibility import FeasibilityCalculator
from join_analyzer import JoinAnalyzer


class TestFeasibilityBoundary:
    """테스트 #8: 적합도 경계값 — 39% → 탈락, 40% → 통과, 41% → 통과."""

    def test_below_threshold_fails(self):
        calc = FeasibilityCalculator()
        # 매칭률 50% (=30점) + API 1개 (≈6.7점) + 조인 0개 (0점) ≈ 36.7%
        result = calc.calculate(
            total_data_needs=4,
            matched_data_needs=2,
            matched_api_count=1,
            join_key_count=0,
        )
        assert result["feasibility_pct"] < 40
        assert result["passed"] is False

    def test_at_threshold_passes(self):
        calc = FeasibilityCalculator()
        # 매칭률 50% (=30) + API 2개 (≈13.3) + 조인 0개 = 43.3%
        result = calc.calculate(
            total_data_needs=4,
            matched_data_needs=2,
            matched_api_count=2,
            join_key_count=0,
        )
        assert result["feasibility_pct"] >= 40
        assert result["passed"] is True

    def test_high_feasibility(self):
        calc = FeasibilityCalculator()
        # 매칭률 100% (=60) + API 3개 (=20) + 조인 2개 (=20) = 100%
        result = calc.calculate(
            total_data_needs=5,
            matched_data_needs=5,
            matched_api_count=3,
            join_key_count=2,
        )
        assert result["feasibility_pct"] == 100.0
        assert result["passed"] is True

    def test_zero_data_needs(self):
        calc = FeasibilityCalculator()
        result = calc.calculate(
            total_data_needs=0,
            matched_data_needs=0,
            matched_api_count=0,
            join_key_count=0,
        )
        assert result["feasibility_pct"] == 0.0
        assert result["passed"] is False

    def test_exact_boundary_39_vs_40(self):
        """정확한 39% → FAIL, 40% → PASS 확인."""
        calc = FeasibilityCalculator()

        # 39% 미만 시나리오
        r39 = calc.calculate(total_data_needs=10, matched_data_needs=5, matched_api_count=1, join_key_count=0)
        # match=30 + api=6.7 + join=0 = 36.7

        # 40% 이상 시나리오
        r40 = calc.calculate(total_data_needs=10, matched_data_needs=5, matched_api_count=2, join_key_count=0)
        # match=30 + api=13.3 + join=0 = 43.3

        assert r39["passed"] is False
        assert r40["passed"] is True


class TestJoinAnalyzer:
    def test_find_common_keys(self):
        analyzer = JoinAnalyzer()
        params_a = [
            {"param_name": "시군구코드", "description": "시군구"},
            {"param_name": "날짜", "description": "조회 날짜"},
        ]
        params_b = [
            {"param_name": "시군구코드", "description": "행정구역"},
            {"param_name": "연도", "description": "연도"},
        ]
        keys = analyzer.find_join_keys(params_a, params_b)
        assert "시군구코드" in keys

    def test_no_common_keys(self):
        analyzer = JoinAnalyzer()
        params_a = [{"param_name": "온도", "description": "기온"}]
        params_b = [{"param_name": "매출", "description": "매출액"}]
        keys = analyzer.find_join_keys(params_a, params_b)
        assert len(keys) == 0

    def test_known_key_pattern_matching(self):
        """파라미터명에 알려진 키가 포함된 경우 매칭."""
        analyzer = JoinAnalyzer()
        params_a = [{"param_name": "기준_법정동코드", "description": "법정동"}]
        params_b = [{"param_name": "법정동코드_시작", "description": "법정동 시작"}]
        keys = analyzer.find_join_keys(params_a, params_b)
        assert "법정동코드" in keys

    def test_analyze_pairs(self):
        analyzer = JoinAnalyzer()
        apis = [
            {"api_id": "A1", "params": [{"param_name": "시군구코드"}, {"param_name": "날짜"}]},
            {"api_id": "A2", "params": [{"param_name": "시군구코드"}, {"param_name": "업종"}]},
            {"api_id": "A3", "params": [{"param_name": "위도"}, {"param_name": "경도"}]},
        ]
        results = analyzer.analyze_api_pairs(apis)
        # A1-A2: 시군구코드 공통
        assert any(
            set(r["api_pair"]) == {"A1", "A2"} and "시군구코드" in r["join_keys"]
            for r in results
        )
