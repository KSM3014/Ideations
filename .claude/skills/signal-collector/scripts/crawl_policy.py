"""정책 브리핑 크롤러 — RSS 피드 + HTML 폴백.

대한민국 정책 브리핑(정부 정책 뉴스)을 RSS로 수집한다.
RSS 실패 시 HTML 페이지에서 직접 파싱한다.
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

logger = get_logger("crawl_policy")

KST = timezone(timedelta(hours=9))

SOURCE_NAME = "policy"

_RSS_URLS = [
    "https://www.korea.kr/rss/policyBriefingList.xml",
    "https://www.korea.kr/rss/policyBriefing.xml",
]

_HTML_URL = "https://www.korea.kr/news/policyBriefingList.do"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8",
}

_MAX_ITEMS = 15


def _strip_html(text: str) -> str:
    """HTML 태그를 제거한다."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def crawl() -> list[dict[str, Any]]:
    """정책 브리핑 최신 정책 뉴스를 수집한다.

    Returns:
        list[dict]: 각 항목은 아래 키를 가진다:
            - source: str  — 소스 식별자 ("policy")
            - title: str   — 정책 제목
            - url: str     — 정책 상세 URL
            - snippet: str — 정책 요약
            - collected_at: str — ISO 8601 수집 시각 (KST)
    """
    import httpx

    logger.info(
        f"정책 브리핑 크롤링 시작 "
        f"(timeout={SIGNAL_SOURCE_TIMEOUT_SEC}s, retry={RETRY_PLAYWRIGHT})"
    )

    signals: list[dict[str, Any]] = []
    now = datetime.now(KST).isoformat()

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=30,
        follow_redirects=True,
    ) as client:
        # 방법 1: RSS 피드 시도
        signals = await _try_rss(client, now)

        # 방법 2: RSS 실패 시 HTML 파싱
        if not signals:
            logger.info("RSS 실패, HTML 파싱 시도")
            signals = await _try_html(client, now)

    logger.info(f"정책 브리핑 크롤링 완료: {len(signals)}건 수집")
    return signals


async def _try_rss(client, now: str) -> list[dict[str, Any]]:
    """RSS 피드에서 정책 뉴스를 파싱한다."""
    import httpx

    signals: list[dict[str, Any]] = []

    for url in _RSS_URLS:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"RSS HTTP {resp.status_code}: {url}")
                continue
        except Exception as e:
            logger.warning(f"RSS 요청 실패 ({url}): {e}")
            continue

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            logger.warning(f"RSS XML 파싱 실패: {e}")
            continue

        items = root.findall(".//item")
        if not items:
            # Atom 형식 시도
            atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//atom:entry", atom_ns)

        for item in items[:_MAX_ITEMS]:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")

            # Atom 형식 폴백
            if title_el is None:
                atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
                title_el = item.find("atom:title", atom_ns)
                link_el = item.find("atom:link", atom_ns)
                desc_el = item.find("atom:summary", atom_ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

            # link 처리 (RSS vs Atom)
            link = ""
            if link_el is not None:
                link = link_el.text.strip() if link_el.text else link_el.get("href", "")

            snippet = _strip_html(desc)[:300] if desc else ""

            if title:
                signals.append({
                    "source": SOURCE_NAME,
                    "title": title,
                    "url": link,
                    "snippet": snippet[:500],
                    "collected_at": now,
                })

        if signals:
            logger.info(f"RSS 피드 성공: {url} ({len(signals)}건)")
            break

    return signals


async def _try_html(client, now: str) -> list[dict[str, Any]]:
    """HTML 페이지에서 정책 뉴스를 파싱한다."""
    import httpx

    signals: list[dict[str, Any]] = []

    try:
        resp = await client.get(_HTML_URL)
        if resp.status_code != 200:
            logger.warning(f"HTML HTTP {resp.status_code}: {_HTML_URL}")
            return signals
    except Exception as e:
        logger.warning(f"HTML 요청 실패: {e}")
        return signals

    html = resp.text

    # korea.kr 정책 브리핑 페이지 — 링크+제목 패턴 매칭
    # <a href="/news/policyBriefingView.do?newsId=XXX" class="...">제목</a>
    pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*policyBriefingView\.do\?newsId=\d+)["\'][^>]*>'
        r'\s*(.*?)\s*</a>',
        re.DOTALL,
    )

    seen: set[str] = set()
    for match in pattern.finditer(html):
        if len(signals) >= _MAX_ITEMS:
            break

        href = match.group(1).strip()
        title = _strip_html(match.group(2)).strip()

        if not title or title in seen:
            continue
        seen.add(title)

        # 상대 URL → 절대 URL
        if href.startswith("/"):
            href = f"https://www.korea.kr{href}"

        signals.append({
            "source": SOURCE_NAME,
            "title": title,
            "url": href,
            "snippet": "",
            "collected_at": now,
        })

    return signals
