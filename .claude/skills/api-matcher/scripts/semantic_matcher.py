"""의미적 매칭 엔진 — 가설의 데이터 니즈를 임베딩 기반 top-K API에 매칭."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import EMBEDDING_TOP_K
from embedding_utils import EmbeddingService
from logger import get_logger

logger = get_logger("semantic_matcher")


class SemanticMatcher:
    """임베딩 기반 의미적 API 매칭."""

    def __init__(self, embedding_service: EmbeddingService | None = None) -> None:
        self._svc = embedding_service or EmbeddingService()
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._svc.load_model()
            self._svc.load_index()
            self._loaded = True

    def match_data_needs(
        self,
        data_needs: list[dict[str, str]],
        top_k: int = EMBEDDING_TOP_K,
    ) -> list[dict[str, Any]]:
        """데이터 니즈 리스트를 임베딩 검색으로 API에 매칭한다.

        Args:
            data_needs: [{"field_name": ..., "description": ...}, ...]
            top_k: 각 니즈당 반환할 최대 API 수

        Returns:
            [{"field_name": ..., "matched_apis": [{"api_id": ..., "score": ..., "rank": ...}]}]
        """
        self._ensure_loaded()

        results = []
        for need in data_needs:
            query = f"{need.get('field_name', '')} {need.get('description', '')}".strip()
            if not query:
                results.append({"field_name": need.get("field_name", ""), "matched_apis": []})
                continue

            matches = self._svc.search(query, top_k=top_k)
            results.append({
                "field_name": need.get("field_name", ""),
                "matched_apis": matches,
            })
            logger.info(
                f"Matched '{need.get('field_name', '')}': {len(matches)} APIs (top score: {matches[0]['score']:.3f})"
                if matches else f"No matches for '{need.get('field_name', '')}'"
            )

        return results

    def match_hypothesis(
        self,
        hypothesis: dict[str, Any],
        top_k: int = EMBEDDING_TOP_K,
    ) -> dict[str, Any]:
        """단일 가설의 모든 데이터 니즈를 매칭한다.

        Returns:
            {"hypothesis_id": ..., "matches_by_need": [...], "unique_apis": [...]}
        """
        self._ensure_loaded()

        data_needs = hypothesis.get("data_needs", [])
        matches_by_need = self.match_data_needs(data_needs, top_k)

        # 고유 API 집합
        seen = {}
        for m in matches_by_need:
            for api in m["matched_apis"]:
                aid = api["api_id"]
                if aid not in seen or api["score"] > seen[aid]["score"]:
                    seen[aid] = api

        unique_apis = sorted(seen.values(), key=lambda x: x["score"], reverse=True)

        return {
            "hypothesis_id": hypothesis.get("id", ""),
            "matches_by_need": matches_by_need,
            "unique_apis": unique_apis,
        }
