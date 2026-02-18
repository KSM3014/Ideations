"""구현 가능성 산출 — 적합도 % 계산.

적합도 = 매칭률 60% + API 보너스 20% + 조인 보너스 20%
품질 게이트: ≥ 40% 통과.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import FEASIBILITY_PASS_THRESHOLD
from logger import get_logger

logger = get_logger("feasibility")


class FeasibilityCalculator:
    """구현 가능성(적합도) 산출기."""

    def __init__(self, pass_threshold: float = FEASIBILITY_PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def calculate(
        self,
        total_data_needs: int,
        matched_data_needs: int,
        matched_api_count: int,
        join_key_count: int,
    ) -> dict[str, Any]:
        """적합도를 계산한다.

        Args:
            total_data_needs: 총 데이터 니즈 수
            matched_data_needs: 매칭된 데이터 니즈 수
            matched_api_count: 매칭된 고유 API 수
            join_key_count: 발견된 조인 키 수

        Returns:
            {"feasibility_pct": float, "passed": bool, "breakdown": {...}}
        """
        if total_data_needs == 0:
            return {
                "feasibility_pct": 0.0,
                "passed": False,
                "breakdown": {
                    "match_rate": 0.0,
                    "api_bonus": 0.0,
                    "join_bonus": 0.0,
                },
            }

        # 매칭률 (0~1) × 60
        match_rate = matched_data_needs / total_data_needs
        match_score = match_rate * 60

        # API 보너스: 2개 이상이면 최대 20
        api_bonus = min(matched_api_count / 3, 1.0) * 20

        # 조인 보너스: 1개 이상이면 최대 20
        join_bonus = min(join_key_count / 2, 1.0) * 20

        feasibility_pct = match_score + api_bonus + join_bonus

        passed = feasibility_pct >= (self.pass_threshold * 100)

        logger.info(
            f"Feasibility: {feasibility_pct:.1f}% "
            f"(match={match_score:.1f}, api={api_bonus:.1f}, join={join_bonus:.1f}) "
            f"→ {'PASS' if passed else 'FAIL'}"
        )

        return {
            "feasibility_pct": round(feasibility_pct, 1),
            "passed": passed,
            "breakdown": {
                "match_rate": round(match_rate, 3),
                "api_bonus": round(api_bonus, 1),
                "join_bonus": round(join_bonus, 1),
            },
        }
