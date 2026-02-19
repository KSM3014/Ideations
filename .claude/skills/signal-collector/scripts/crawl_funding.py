"""스타트업 펀딩 크롤러 — RSS + HTML 폴백.

한국 스타트업 투자/펀딩 뉴스를 수집한다.
Platum(WordPress) RSS 피드를 우선 시도, 실패 시 HTML 파싱.
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

logger = get_logger("crawl_funding")

KST = timezone(timedelta(hours=9))

SOURCE_NAME = "funding"

# Platum WordPress RSS 피드
_RSS_URLS = [
    "https://platum.kr/feed",
    "https://platum.kr/archives/category/startup-news/feed",
]

_HTML_URL = "https://platum.kr/archives/category/startup-news"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html, application/xhtml+xml, application/xml;q=0.9, */*;q=0.8",
}

_MAX_ITEMS = 15

# 펀딩 관련 키워드 — 관련성 필터링용
_FUNDING_KEYWORDS = [
    "투자", "펀딩", "시리즈", "시드", "라운드", "인수", "합병",
    "IPO", "상장", "유치", "조달", "억원", "백만", "million",
    "funding", "invest", "series", "seed", "round", "acquisition",
]


def _strip_html(text: str) -> str:
    """HTML 태그를 제거한다."""
    cleaned = re.sub(r"<[^>]+>", "", text)
    # CDATA 정리
    cleaned = cleaned.replace("<![CDATA[", "").replace("]]>", "")
    return cleaned.strip()


def _is_funding_related(title: str, desc: str) -> bool:
    """펀딩 관련 기사인지 판별한다."""
    combined = (title + " " + desc).lower()
    return any(kw.lower() in combined for kw in _FUNDING_KEYWORDS)


async def crawl() -> list[dict[str, Any]]:
    """스타트업 펀딩/투자 뉴스를 수집한다.

    Returns:
        list[dict]: 각 항목은 아래 키를 가진다:
            - source: str  — 소스 식별자 ("funding")
            - title: str   — 펀딩 뉴스 제목
            - url: str     — 뉴스 상세 URL
            - snippet: str — 투자 금액/라운드 요약
            - collected_at: str — ISO 8601 수집 시각 (KST)
    """
    import httpx

    logger.info(
        f"스타트업 펀딩 크롤링 시작 "
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

    logger.info(f"스타트업 펀딩 크롤링 완료: {len(signals)}건 수집")
    return signals


async def _try_rss(client, now: str) -> list[dict[str, Any]]:
    """RSS 피드에서 펀딩 뉴스를 파싱한다."""
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
            # CDATA가 포함된 경우 처리
            xml_text = resp.text
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"RSS XML 파싱 실패: {e}")
            continue

        items = root.findall(".//item")

        for item in items[:_MAX_ITEMS * 2]:  # 필터링 전 여유분
            if len(signals) >= _MAX_ITEMS:
                break

            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

            if not title:
                continue

            snippet = _strip_html(desc)[:300]
            if pub_date:
                snippet = f"[{pub_date}] {snippet}"

            # /feed 전체 피드에서는 펀딩 관련만 필터
            if "startup-news" not in url and not _is_funding_related(title, desc):
                continue

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
    """HTML 페이지에서 펀딩 뉴스를 파싱한다."""
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

    # Platum 기사 패턴: <a href="https://platum.kr/archives/XXXXX">제목</a>
    pattern = re.compile(
        r'<a[^>]+href=["\']'
        r'(https?://platum\.kr/archives/\d+)'
        r'["\'][^>]*>\s*(.*?)\s*</a>',
        re.DOTALL,
    )

    seen: set[str] = set()
    for match in pattern.finditer(html):
        if len(signals) >= _MAX_ITEMS:
            break

        href = match.group(1).strip()
        title = _strip_html(match.group(2)).strip()

        if not title or len(title) < 5 or href in seen:
            continue
        seen.add(href)

        signals.append({
            "source": SOURCE_NAME,
            "title": title,
            "url": href,
            "snippet": "",
            "collected_at": now,
        })

    return signals
