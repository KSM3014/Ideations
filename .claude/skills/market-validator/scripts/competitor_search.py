"""경쟁사 검색 — Playwright 기반 Google 검색 (스텁).

비동기로 경쟁사/유사 서비스를 검색하여 name, url, snippet 형태로 반환한다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from logger import get_logger

logger = get_logger("competitor_search")


class CompetitorSearcher:
    """Playwright 기반 Google 검색으로 경쟁사를 탐색한다 (현재 스텁)."""

    def __init__(self, max_results: int = 10) -> None:
        self.max_results = max_results

    async def search(self, query: str) -> list[dict[str, Any]]:
        """경쟁사/유사 서비스를 검색한다.

        Args:
            query: 검색 키워드 (예: "실시간 교통 모니터링 서비스")

        Returns:
            [{"name": ..., "url": ..., "snippet": ...}, ...]
        """
        logger.info(f"Competitor search (stub): query='{query}'")

        # TODO: Playwright 기반 실제 Google 검색 구현
        # - headless 브라우저로 Google 검색
        # - 검색 결과 파싱하여 name, url, snippet 추출
        # - RETRY_PLAYWRIGHT 설정 적용
        results: list[dict[str, Any]] = []

        logger.info(f"Competitor search returned {len(results)} results")
        return results

    async def search_with_variants(self, base_query: str, variants: list[str] | None = None) -> list[dict[str, Any]]:
        """기본 쿼리와 변형 쿼리를 모두 검색하여 중복 제거 후 반환한다.

        Args:
            base_query: 기본 검색 키워드
            variants: 추가 검색 변형 (없으면 기본 변형 생성)

        Returns:
            중복 제거된 경쟁사 리스트
        """
        if variants is None:
            variants = [
                f"{base_query} 서비스",
                f"{base_query} 플랫폼",
                f"{base_query} SaaS",
            ]

        all_results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for query in [base_query] + variants:
            results = await self.search(query)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)

        logger.info(
            f"Combined search: {len(all_results)} unique results "
            f"from {1 + len(variants)} queries"
        )
        return all_results
