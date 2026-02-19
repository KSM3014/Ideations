"""경쟁사 검색 — DuckDuckGo HTML 검색 기반.

비동기로 경쟁사/유사 서비스를 검색하여 name, url, snippet 형태로 반환한다.
"""

from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, unquote

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx

from logger import get_logger

logger = get_logger("competitor_search")

_DDG_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
_TIMEOUT = 15


def _parse_ddg_html(html: str, max_results: int = 10) -> list[dict[str, Any]]:
    """DuckDuckGo HTML 검색 결과를 파싱한다."""
    results: list[dict[str, Any]] = []

    # 각 결과 블록: <a class="result__a" href="...">title</a>
    # snippet: <a class="result__snippet" ...>...</a>
    link_pattern = re.compile(
        r'<a\s+[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    snippet_pattern = re.compile(
        r'<a\s+[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i, (raw_url, raw_title) in enumerate(links[:max_results]):
        # DuckDuckGo URL 디코딩 (리다이렉트 URL에서 실제 URL 추출)
        url = raw_url
        if "uddg=" in url:
            match = re.search(r"uddg=([^&]+)", url)
            if match:
                url = unquote(match.group(1))

        # HTML 태그 제거
        title = re.sub(r"<[^>]+>", "", raw_title).strip()
        title = unescape(title)

        snippet = ""
        if i < len(snippets):
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            snippet = unescape(snippet)

        if url and title:
            results.append({
                "name": title,
                "url": url,
                "snippet": snippet,
            })

    return results


class CompetitorSearcher:
    """DuckDuckGo HTML 검색으로 경쟁사를 탐색한다."""

    def __init__(self, max_results: int = 10) -> None:
        self.max_results = max_results

    async def search(self, query: str) -> list[dict[str, Any]]:
        """경쟁사/유사 서비스를 검색한다.

        Args:
            query: 검색 키워드 (예: "실시간 교통 모니터링 서비스")

        Returns:
            [{"name": ..., "url": ..., "snippet": ...}, ...]
        """
        logger.info(f"Competitor search: query='{query}'")

        try:
            async with httpx.AsyncClient(
                headers=_HEADERS,
                timeout=_TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = await client.post(
                    _DDG_URL,
                    data={"q": query, "kl": "kr-kr"},
                )
                resp.raise_for_status()
                results = _parse_ddg_html(resp.text, self.max_results)

        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            results = []

        logger.info(f"Competitor search returned {len(results)} results")
        return results

    async def search_with_variants(
        self, base_query: str, variants: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """기본 쿼리와 변형 쿼리를 모두 검색하여 중복 제거 후 반환한다."""
        if variants is None:
            variants = [
                f"{base_query} 서비스",
                f"{base_query} 플랫폼",
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
