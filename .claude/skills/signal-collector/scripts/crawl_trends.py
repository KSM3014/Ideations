"""Google Trends Korea 크롤러 — RSS 피드 기반.

Google Trends KR 일간 인기 검색어를 RSS 피드로 수집한다.
Playwright 불필요 — 공개 RSS 엔드포인트를 httpx로 요청.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import SIGNAL_SOURCE_TIMEOUT_SEC, RETRY_PLAYWRIGHT
from logger import get_logger

logger = get_logger("crawl_trends")

KST = timezone(timedelta(hours=9))

SOURCE_NAME = "google_trends"

_RSS_URLS = [
    "https://trends.google.co.kr/trending/rss?geo=KR",
    "https://trends.google.com/trending/rss?geo=KR",
    "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KR",
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_MAX_ITEMS = 20


def _text(element: ET.Element, tag: str, ns: dict[str, str] | None = None) -> str | None:
    """XML 엘리먼트에서 텍스트를 추출한다."""
    child = element.find(tag, ns or {})
    if child is not None and child.text:
        return child.text.strip()
    return None


def _strip_html(text: str) -> str:
    """HTML 태그를 제거한다."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def crawl() -> list[dict[str, Any]]:
    """Google Trends KR 일간 인기 검색어를 수집한다.

    Returns:
        list[dict]: 각 항목은 아래 키를 가진다:
            - source: str  — 소스 식별자 ("google_trends")
            - title: str   — 트렌드 키워드/제목
            - url: str     — 트렌드 상세 URL
            - snippet: str — 관련 요약 텍스트
            - collected_at: str — ISO 8601 수집 시각 (KST)
    """
    import httpx

    logger.info(
        f"Google Trends KR 크롤링 시작 "
        f"(timeout={SIGNAL_SOURCE_TIMEOUT_SEC}s, retry={RETRY_PLAYWRIGHT})"
    )

    signals: list[dict[str, Any]] = []
    now = datetime.now(KST).isoformat()

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=30,
        follow_redirects=True,
    ) as client:
        xml_text = None

        for url in _RSS_URLS:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and resp.text.strip():
                    xml_text = resp.text
                    logger.info(f"RSS 피드 성공: {url}")
                    break
                logger.warning(f"RSS HTTP {resp.status_code}: {url}")
            except Exception as e:
                logger.warning(f"RSS 요청 실패 ({url}): {e}")
                continue

        if not xml_text:
            logger.warning("모든 Google Trends RSS URL 실패")
            return signals

        # XML 파싱
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"RSS XML 파싱 실패: {e}")
            return signals

        # Google Trends RSS 네임스페이스
        ns: dict[str, str] = {}
        for prefix, uri in _iter_namespaces(xml_text):
            if "trends" in uri.lower() or prefix == "ht":
                ns["ht"] = uri
        if not ns:
            ns = {"ht": "https://trends.google.com/trending/rss"}

        # RSS feed의 channel link (무시해야 함 — 모든 item에 동일)
        channel_link = ""
        channel_el = root.find(".//channel/link")
        if channel_el is not None and channel_el.text:
            channel_link = channel_el.text.strip()

        # RSS 2.0: channel > item
        items = root.findall(".//item")

        for item in items[:_MAX_ITEMS]:
            title = _text(item, "title") or ""

            # 트래픽 정보
            traffic = _text(item, "ht:approx_traffic", ns) or ""

            # 뉴스 기사 URL과 스니펫 추출 (ht:news_item)
            link = ""
            snippet_parts: list[str] = []
            news_items = item.findall("ht:news_item", ns)
            for ni in news_items[:2]:  # 최대 2개 뉴스
                ni_title = _text(ni, "ht:news_item_title", ns) or ""
                ni_url = _text(ni, "ht:news_item_url", ns) or ""
                ni_source = _text(ni, "ht:news_item_source", ns) or ""
                if ni_title:
                    part = ni_title
                    if ni_source:
                        part += f" ({ni_source})"
                    snippet_parts.append(part)
                if not link and ni_url:
                    link = ni_url

            # link 폴백: Google Trends 검색 URL
            if not link:
                from urllib.parse import quote
                link = f"https://trends.google.co.kr/trending?geo=KR&q={quote(title)}"

            snippet = " | ".join(snippet_parts) if snippet_parts else f"인기 검색어: {title}"
            if traffic:
                snippet = f"[{traffic} 검색] {snippet}"

            if title:
                signals.append({
                    "source": SOURCE_NAME,
                    "title": title.strip(),
                    "url": link.strip(),
                    "snippet": snippet.strip()[:500],
                    "collected_at": now,
                })

    logger.info(f"Google Trends KR 크롤링 완료: {len(signals)}건 수집")
    return signals


def _iter_namespaces(xml_text: str):
    """XML 텍스트에서 네임스페이스 선언을 추출한다."""
    for match in re.finditer(r'xmlns:(\w+)=["\']([^"\']+)["\']', xml_text):
        yield match.group(1), match.group(2)
