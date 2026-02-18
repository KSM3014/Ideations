"""시장 프록시 스코어링 — 간접 시장 지표 기반 점수 산출.

평가 항목: similar_services_count, target_community_size, search_trend.
만점: 25점.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from logger import get_logger

logger = get_logger("market_proxy_scorer")

# 프록시 지표별 배점 (합계 25)
_PROXY_WEIGHTS = {
    "similar_services_count": 10,  # 유사 서비스 수 (경쟁 존재 = 시장 존재)
    "target_community_size": 8,    # 타깃 커뮤니티 규모
    "search_trend": 7,             # 검색 트렌드 (관심도)
}


class MarketProxyScorer:
    """간접 시장 지표를 기반으로 시장 존재 가능성 점수를 산출한다."""

    MAX_SCORE = 25.0

    def __init__(self) -> None:
        self.weights = _PROXY_WEIGHTS

    def score(self, proxies: dict[str, Any]) -> float:
        """프록시 지표 딕셔너리를 기반으로 시장 점수를 계산한다.

        Args:
            proxies: {
                "similar_services_count": int,    # 발견된 유사 서비스 수 (0~10+)
                "target_community_size": str,     # "small" | "medium" | "large"
                "search_trend": str,              # "declining" | "stable" | "rising"
            }

        Returns:
            시장 프록시 점수 (0~25).
        """
        total = 0.0

        # 1. 유사 서비스 수 (0~10점)
        similar_count = proxies.get("similar_services_count", 0)
        if similar_count >= 5:
            svc_score = self.weights["similar_services_count"]
        elif similar_count >= 3:
            svc_score = self.weights["similar_services_count"] * 0.8
        elif similar_count >= 1:
            svc_score = self.weights["similar_services_count"] * 0.5
        else:
            svc_score = 0.0
        total += svc_score

        # 2. 타깃 커뮤니티 규모 (0~8점)
        community = proxies.get("target_community_size", "small")
        community_map = {
            "large": 1.0,
            "medium": 0.6,
            "small": 0.3,
        }
        community_ratio = community_map.get(community, 0.3)
        community_score = self.weights["target_community_size"] * community_ratio
        total += community_score

        # 3. 검색 트렌드 (0~7점)
        trend = proxies.get("search_trend", "stable")
        trend_map = {
            "rising": 1.0,
            "stable": 0.5,
            "declining": 0.2,
        }
        trend_ratio = trend_map.get(trend, 0.5)
        trend_score = self.weights["search_trend"] * trend_ratio
        total += trend_score

        total = round(min(total, self.MAX_SCORE), 1)

        logger.info(
            f"Market proxy score: {total}/{self.MAX_SCORE} "
            f"(services={svc_score:.1f}, community={community_score:.1f}, "
            f"trend={trend_score:.1f})"
        )

        return total
