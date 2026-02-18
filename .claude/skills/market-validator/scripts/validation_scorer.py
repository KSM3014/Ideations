"""검증 점수 산출 — Phase 4 시장 검증 종합 스코어.

총 100점 배분:
  - competitor_analysis: 25점
  - market_demand_proxy: 25점
  - timing_fit: 20점
  - revenue_reference: 15점
  - mvp_difficulty: 15점

품질 게이트: >= 50점 통과.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import VALIDATION_PASS_THRESHOLD
from logger import get_logger

logger = get_logger("validation_scorer")

# 항목별 만점
_CATEGORY_MAX = {
    "competitor_analysis": 25,
    "market_demand_proxy": 25,
    "timing_fit": 20,
    "revenue_reference": 15,
    "mvp_difficulty": 15,
}


class ValidationScorer:
    """시장 검증 종합 점수를 산출한다."""

    TOTAL_MAX = 100
    PASS_THRESHOLD = VALIDATION_PASS_THRESHOLD  # config에서 가져옴 (기본 50)

    def calculate(
        self,
        hypothesis_data: dict[str, Any],
        competitors: list[dict[str, Any]],
        proxy_score: float,
    ) -> dict[str, Any]:
        """검증 종합 점수를 계산한다.

        Args:
            hypothesis_data: 가설 정보 {
                "timing_fit": float (0~1),
                "revenue_reference": float (0~1),
                "mvp_difficulty": float (0~1),
            }
            competitors: 경쟁사 리스트 [{"name": ..., "url": ..., "snippet": ...}]
            proxy_score: 시장 프록시 점수 (0~25, MarketProxyScorer의 결과)

        Returns:
            {
                "total_score": float,
                "passed": bool,
                "breakdown": {
                    "competitor_analysis": float,
                    "market_demand_proxy": float,
                    "timing_fit": float,
                    "revenue_reference": float,
                    "mvp_difficulty": float,
                },
                "threshold": int,
            }
        """
        breakdown: dict[str, float] = {}

        # 1. 경쟁사 분석 (25점)
        breakdown["competitor_analysis"] = self._score_competitors(competitors)

        # 2. 시장 수요 프록시 (25점) — 이미 계산된 proxy_score 사용
        breakdown["market_demand_proxy"] = round(
            min(proxy_score, _CATEGORY_MAX["market_demand_proxy"]), 1
        )

        # 3. 타이밍 적합도 (20점)
        timing_ratio = float(hypothesis_data.get("timing_fit", 0.5))
        breakdown["timing_fit"] = round(
            timing_ratio * _CATEGORY_MAX["timing_fit"], 1
        )

        # 4. 수익 모델 참조 (15점)
        revenue_ratio = float(hypothesis_data.get("revenue_reference", 0.5))
        breakdown["revenue_reference"] = round(
            revenue_ratio * _CATEGORY_MAX["revenue_reference"], 1
        )

        # 5. MVP 난이도 (15점) — 낮을수록 좋음 (쉬울수록 고점)
        mvp_ratio = float(hypothesis_data.get("mvp_difficulty", 0.5))
        breakdown["mvp_difficulty"] = round(
            mvp_ratio * _CATEGORY_MAX["mvp_difficulty"], 1
        )

        total_score = round(sum(breakdown.values()), 1)
        passed = total_score >= self.PASS_THRESHOLD

        logger.info(
            f"Validation score: {total_score}/{self.TOTAL_MAX} "
            f"→ {'PASS' if passed else 'FAIL'} "
            f"(threshold={self.PASS_THRESHOLD})"
        )

        return {
            "total_score": total_score,
            "passed": passed,
            "breakdown": breakdown,
            "threshold": self.PASS_THRESHOLD,
        }

    def _score_competitors(self, competitors: list[dict[str, Any]]) -> float:
        """경쟁사 리스트 기반 경쟁 분석 점수를 산출한다.

        경쟁사 존재 = 시장 존재 증거, 그러나 과다하면 레드오션.
        - 0개: 시장 불확실 → 10점
        - 1~3개: 블루오션 → 25점
        - 4~7개: 적정 경쟁 → 20점
        - 8~15개: 경쟁 과열 → 12점
        - 16+개: 레드오션 → 5점
        """
        count = len(competitors)

        if count == 0:
            score = 10.0
        elif count <= 3:
            score = 25.0
        elif count <= 7:
            score = 20.0
        elif count <= 15:
            score = 12.0
        else:
            score = 5.0

        return score
