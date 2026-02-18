"""NUMR-V 가중 점수 산출 — Novelty, Utility, Market, Realizability, Validation.

가중치: N×0.10, U×0.20, M×0.20, R×0.25, V×0.25 (config.NUMRV_WEIGHTS).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import NUMRV_WEIGHTS
from logger import get_logger

logger = get_logger("numrv_scorer")


class NUMRVScorer:
    """NUMR-V 가중 종합 점수를 산출한다."""

    DIMENSIONS = ("N", "U", "M", "R", "V")

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or NUMRV_WEIGHTS

    def calculate_weighted_score(self, scores: dict[str, float]) -> float:
        """각 차원의 원점수(0~5)를 가중 합산하여 종합 점수를 반환한다.

        Args:
            scores: {"N": float, "U": float, "M": float, "R": float, "V": float}
                    각 값은 0~5 범위.

        Returns:
            가중 종합 점수 (0~5).
        """
        total = 0.0
        for dim in self.DIMENSIONS:
            raw = scores.get(dim, 0.0)
            weight = self.weights.get(dim, 0.0)
            total += raw * weight

        total = round(total, 4)

        logger.info(
            f"NUMR-V weighted score: {total:.4f} "
            f"(N={scores.get('N', 0)}, U={scores.get('U', 0)}, "
            f"M={scores.get('M', 0)}, R={scores.get('R', 0)}, "
            f"V={scores.get('V', 0)})"
        )

        return total

    def score_batch(self, ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """아이디어 배치의 종합 점수를 일괄 산출한다.

        Args:
            ideas: [{"id": ..., "scores": {"N": ..., "U": ..., ...}}, ...]

        Returns:
            원본에 "weighted_score" 필드가 추가된 리스트.
        """
        for idea in ideas:
            scores = idea.get("scores", {})
            idea["weighted_score"] = self.calculate_weighted_score(scores)

        return ideas
