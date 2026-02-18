"""MVP 게이트 테스트 — Phase 4 검증 점수 경계값 (49→실패, 50→통과, 51→통과)."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_VALIDATOR_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "market-validator" / "scripts"
if str(_VALIDATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_VALIDATOR_SCRIPTS))

from validation_scorer import ValidationScorer
from market_proxy_scorer import MarketProxyScorer


class TestValidationScoreBoundary:
    """검증 점수 경계값 — 49 → FAIL, 50 → PASS, 51 → PASS."""

    def _make_result(self, target_score: float) -> dict:
        """지정된 총점에 근사하는 검증 결과를 생성한다.

        경쟁사 2개(=25), proxy_score + timing + revenue + mvp로 나머지 조정.
        """
        scorer = ValidationScorer()

        # competitor_analysis = 25 (경쟁사 2개)
        competitors = [
            {"name": "서비스A", "url": "https://a.com", "snippet": "설명A"},
            {"name": "서비스B", "url": "https://b.com", "snippet": "설명B"},
        ]

        # 나머지 = target_score - 25
        remaining = target_score - 25.0

        # proxy_score(max 25), timing(max 20), revenue(max 15), mvp(max 15)
        # timing_fit, revenue_reference, mvp_difficulty 는 비율(0~1)
        # timing=20*ratio, revenue=15*ratio, mvp=15*ratio
        # remaining = proxy + 20*t + 15*r + 15*m

        # proxy = remaining * 0.5 방식으로 분배
        proxy_score = min(remaining * 0.5, 25.0)
        after_proxy = remaining - proxy_score

        # timing, revenue, mvp 균등 분배
        if after_proxy <= 0:
            timing_ratio = 0.0
            revenue_ratio = 0.0
            mvp_ratio = 0.0
        else:
            per_each = after_proxy / 3.0
            timing_ratio = min(per_each / 20.0, 1.0)
            revenue_ratio = min(per_each / 15.0, 1.0)
            mvp_ratio = min(per_each / 15.0, 1.0)

        hypothesis_data = {
            "timing_fit": timing_ratio,
            "revenue_reference": revenue_ratio,
            "mvp_difficulty": mvp_ratio,
        }

        return scorer.calculate(hypothesis_data, competitors, proxy_score)

    def test_score_49_fails(self):
        """총점 49 → FAIL."""
        result = self._make_result(49.0)
        assert result["total_score"] < 50, f"Expected <50, got {result['total_score']}"
        assert result["passed"] is False

    def test_score_50_passes(self):
        """총점 50 → PASS."""
        result = self._make_result(50.0)
        assert result["total_score"] >= 50, f"Expected >=50, got {result['total_score']}"
        assert result["passed"] is True

    def test_score_51_passes(self):
        """총점 51 → PASS."""
        result = self._make_result(51.0)
        assert result["total_score"] >= 50, f"Expected >=50, got {result['total_score']}"
        assert result["passed"] is True

    def test_exact_threshold_boundary(self):
        """정확한 경계값 직접 검증 — threshold=50 기준."""
        scorer = ValidationScorer()

        # 정확히 49점: competitor=10(0개) + proxy=15 + timing=0.6*20=12 + revenue=0.8*15=12 + mvp=0*15=0
        # = 10 + 15 + 12 + 12 + 0 = 49
        r49 = scorer.calculate(
            {"timing_fit": 0.6, "revenue_reference": 0.8, "mvp_difficulty": 0.0},
            [],  # 0 competitors = 10점
            15.0,
        )
        assert r49["total_score"] == 49.0
        assert r49["passed"] is False

        # 정확히 50점: competitor=10(0개) + proxy=15 + timing=0.6*20=12 + revenue=0.8*15=12 + mvp=1/15
        # mvp_ratio = 1/15 → 15*(1/15)=1.0
        # 10 + 15 + 12 + 12 + 1 = 50
        r50 = scorer.calculate(
            {"timing_fit": 0.6, "revenue_reference": 0.8, "mvp_difficulty": 1 / 15},
            [],
            15.0,
        )
        assert r50["total_score"] == 50.0
        assert r50["passed"] is True

        # 정확히 51점: mvp_difficulty = 2/15 → 15*(2/15) = 2.0
        # 10 + 15 + 12 + 12 + 2 = 51
        r51 = scorer.calculate(
            {"timing_fit": 0.6, "revenue_reference": 0.8, "mvp_difficulty": 2 / 15},
            [],
            15.0,
        )
        assert r51["total_score"] == 51.0
        assert r51["passed"] is True


class TestMarketProxyScorer:
    """시장 프록시 스코어러 기본 테스트."""

    def test_max_score(self):
        scorer = MarketProxyScorer()
        score = scorer.score({
            "similar_services_count": 10,
            "target_community_size": "large",
            "search_trend": "rising",
        })
        assert score == 25.0

    def test_min_score(self):
        scorer = MarketProxyScorer()
        score = scorer.score({
            "similar_services_count": 0,
            "target_community_size": "small",
            "search_trend": "declining",
        })
        assert score > 0  # community(small=0.3*8=2.4) + trend(declining=0.2*7=1.4) = 3.8
        assert score < 5

    def test_medium_scenario(self):
        scorer = MarketProxyScorer()
        score = scorer.score({
            "similar_services_count": 3,
            "target_community_size": "medium",
            "search_trend": "stable",
        })
        assert 5 < score < 20
