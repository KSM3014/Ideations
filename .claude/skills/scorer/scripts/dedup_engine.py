"""중복 탐지 엔진 — 코사인 유사도 기반 아이디어 중복 판정.

임계값: config.DEDUP_SIMILARITY_THRESHOLD (기본 0.85).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import DEDUP_SIMILARITY_THRESHOLD
from logger import get_logger

logger = get_logger("dedup_engine")


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """두 벡터의 코사인 유사도를 계산한다."""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


class DedupEngine:
    """코사인 유사도 기반 아이디어 중복 탐지기."""

    def __init__(self, threshold: float = DEDUP_SIMILARITY_THRESHOLD) -> None:
        self.threshold = threshold

    def check_duplicates(
        self,
        current_ideas: list[dict[str, Any]],
        archive_embeddings: np.ndarray | None = None,
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """현재 아이디어를 아카이브 임베딩과 비교하여 중복을 표시한다.

        Args:
            current_ideas: [{"id": ..., "embedding": np.ndarray, ...}, ...]
                           각 아이디어에 "embedding" 키가 있어야 함.
            archive_embeddings: (N, D) 형태의 아카이브 임베딩 행렬.
                               None이면 중복 없음으로 판정.
            threshold: 유사도 임계값 (None이면 self.threshold 사용).

        Returns:
            각 아이디어에 "is_duplicate", "max_similarity" 필드가 추가된 리스트.
        """
        thresh = threshold if threshold is not None else self.threshold

        if archive_embeddings is None or len(archive_embeddings) == 0:
            for idea in current_ideas:
                idea["is_duplicate"] = False
                idea["max_similarity"] = 0.0
            logger.info("No archive embeddings — all ideas marked as unique")
            return current_ideas

        dup_count = 0
        for idea in current_ideas:
            emb = idea.get("embedding")
            if emb is None:
                idea["is_duplicate"] = False
                idea["max_similarity"] = 0.0
                continue

            emb = np.asarray(emb)

            # 아카이브 전체와 코사인 유사도 계산
            similarities = np.array([
                _cosine_similarity(emb, arch_emb)
                for arch_emb in archive_embeddings
            ])

            max_sim = float(np.max(similarities)) if len(similarities) > 0 else 0.0
            is_dup = max_sim >= thresh

            idea["is_duplicate"] = is_dup
            idea["max_similarity"] = round(max_sim, 4)

            if is_dup:
                dup_count += 1

        logger.info(
            f"Dedup check: {dup_count}/{len(current_ideas)} duplicates "
            f"(threshold={thresh})"
        )

        return current_ideas
