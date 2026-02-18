"""등급 분류기 — 하이브리드(절대 하한 + 상대 백분위) 등급 부여.

등급 기준:
  S: top 10% AND score >= 4.0
  A: top 30% AND score >= 3.2
  B: score >= 2.5
  C: score >= 1.5
  D: score < 1.5
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import GRADE_ABSOLUTE, GRADE_PERCENTILE
from logger import get_logger

logger = get_logger("grade_classifier")


class GradeClassifier:
    """하이브리드 등급 분류기 — 절대 하한 + 상대 백분위."""

    def __init__(
        self,
        absolute: dict[str, float] | None = None,
        percentile: dict[str, int] | None = None,
    ) -> None:
        self.absolute = absolute or GRADE_ABSOLUTE
        self.percentile = percentile or GRADE_PERCENTILE

    def classify(self, scored_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """점수가 매겨진 아이디어 리스트에 등급을 부여한다.

        Args:
            scored_ideas: [{"id": ..., "weighted_score": float, ...}, ...]

        Returns:
            각 아이디어에 "grade" 필드가 추가된 리스트.
        """
        if not scored_ideas:
            return scored_ideas

        # 점수 기준 내림차순 정렬 (순위 산정용)
        scores = [idea.get("weighted_score", 0.0) for idea in scored_ideas]
        sorted_scores = sorted(scores, reverse=True)
        n = len(sorted_scores)

        for idea in scored_ideas:
            score = idea.get("weighted_score", 0.0)
            rank = sorted_scores.index(score) + 1  # 1-based rank
            percentile_rank = (rank / n) * 100  # 상위 N%

            grade = self._assign_grade(score, percentile_rank)
            idea["grade"] = grade

        grade_dist = {}
        for idea in scored_ideas:
            g = idea["grade"]
            grade_dist[g] = grade_dist.get(g, 0) + 1

        logger.info(f"Grade classification: {grade_dist} (total={n})")

        return scored_ideas

    def _assign_grade(self, score: float, percentile_rank: float) -> str:
        """단일 아이디어의 등급을 결정한다.

        Args:
            score: 가중 종합 점수.
            percentile_rank: 상위 백분위 (1이 최고).

        Returns:
            "S" | "A" | "B" | "C" | "D"
        """
        # S: top 10% AND score >= 4.0
        if percentile_rank <= self.percentile["S"] and score >= self.absolute["S"]:
            return "S"

        # A: top 30% AND score >= 3.2
        if percentile_rank <= self.percentile["A"] and score >= self.absolute["A"]:
            return "A"

        # B: score >= 2.5
        if score >= self.absolute["B"]:
            return "B"

        # C: score >= 1.5
        if score >= self.absolute["C"]:
            return "C"

        # D: score < 1.5
        return "D"
