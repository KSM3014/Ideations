"""Google News KO 크롤러 — RSS 피드 기반.

Google News 한국어 기술/스타트업 섹션을 RSS 피드로 수집한다.
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

logger = get_logger("crawl_news")

KST = timezone(timedelta(hours=9))

SOURCE_NAME = "news"

# Google News RSS — 여러 쿼리로 다양한 신호 수집
_RSS_FEEDS = [
    {
        "label": "스타트업/기술",
        "url": (
            "https://news.google.com/rss/search?"
            "q=%EC%8A%A4%ED%83%80%ED%8A%B8%EC%97%85+OR+%EA%B8%B0%EC%88%A0+OR+AI"
            "&hl=ko&gl=KR&ceid=KR:ko"
        ),
    },
    {
        "label": "공공데이터/API",
        "url": (
            "https://news.google.com/rss/search?"
            "q=%EA%B3%B5%EA%B3%B5%EB%8D%B0%EC%9D%B4%ED%84%B0+OR+%EC%98%A4%ED%94%88API"
            "&hl=ko&gl=KR&ceid=KR:ko"
        ),
    },
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_MAX_ITEMS_PER_FEED = 10


def _strip_html(text: str) -> str:
    """HTML 태그를 제거한다."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def crawl() -> list[dict[str, Any]]:
    """Google News KO 기술/스타트업 기사를 수집한다.

    Returns:
        list[dict]: 각 항목은 아래 키를 가진다:
            - source: str  — 소스 식별자 ("news")
            - title: str   — 기사 제목
            - url: str     — 기사 URL
            - snippet: str — 기사 요약/리드
            - collected_at: str — ISO 8601 수집 시각 (KST)
    """
    import httpx

    logger.info(
        f"Google News KO 크롤링 시작 "
        f"(timeout={SIGNAL_SOURCE_TIMEOUT_SEC}s, feeds={len(_RSS_FEEDS)})"
    )

    signals: list[dict[str, Any]] = []
    now = datetime.now(KST).isoformat()
    seen_titles: set[str] = set()

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=30,
        follow_redirects=True,
    ) as client:
        for feed_info in _RSS_FEEDS:
            label = feed_info["label"]
            url = feed_info["url"]

            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"[{label}] RSS HTTP {resp.status_code}")
                    continue
            except Exception as e:
                logger.warning(f"[{label}] RSS 요청 실패: {e}")
                continue

            # XML 파싱
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError as e:
                logger.warning(f"[{label}] XML 파싱 실패: {e}")
                continue

            items = root.findall(".//item")
            count = 0

            for item in items:
                if count >= _MAX_ITEMS_PER_FEED:
                    break

                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                pub_el = item.find("pubDate")

                title = title_el.text.strip() if title_el is not None and title_el.text else ""
                link = link_el.text.strip() if link_el is not None and link_el.text else ""
                desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

                if not title or title in seen_titles:
                    continue

                seen_titles.add(title)

                # description에서 HTML 제거
                snippet = _strip_html(desc)[:300] if desc else ""
                if pub_date:
                    snippet = f"[{pub_date}] {snippet}" if snippet else pub_date

                signals.append({
                    "source": SOURCE_NAME,
                    "title": title,
                    "url": link,
                    "snippet": snippet[:500],
                    "collected_at": now,
                })
                count += 1

            logger.info(f"[{label}] {count}건 파싱 완료")

    logger.info(f"Google News KO 크롤링 완료: {len(signals)}건 수집")
    return signals
