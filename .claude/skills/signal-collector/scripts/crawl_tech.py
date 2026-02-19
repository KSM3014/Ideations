"""Hacker News 크롤러 — 공개 JSON API 기반.

Hacker News 프론트페이지 Top Stories를 Firebase API로 수집한다.
Playwright 불필요 — 공개 JSON API를 httpx로 요청.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import SIGNAL_SOURCE_TIMEOUT_SEC, RETRY_PLAYWRIGHT
from logger import get_logger

logger = get_logger("crawl_tech")

KST = timezone(timedelta(hours=9))

SOURCE_NAME = "tech"

_HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}

_MAX_STORIES = 15
_CONCURRENT_FETCHES = 5


async def crawl() -> list[dict[str, Any]]:
    """Hacker News 프론트페이지 Top Stories를 수집한다.

    Returns:
        list[dict]: 각 항목은 아래 키를 가진다:
            - source: str  — 소스 식별자 ("tech")
            - title: str   — 게시물 제목
            - url: str     — 상세 URL
            - snippet: str — 점수/댓글 수 요약
            - collected_at: str — ISO 8601 수집 시각 (KST)
    """
    import httpx

    logger.info(
        f"Hacker News 크롤링 시작 "
        f"(timeout={SIGNAL_SOURCE_TIMEOUT_SEC}s, max_stories={_MAX_STORIES})"
    )

    signals: list[dict[str, Any]] = []
    now = datetime.now(KST).isoformat()

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=20,
        follow_redirects=True,
    ) as client:
        # 1. Top Stories ID 목록 가져오기
        try:
            resp = await client.get(_HN_TOP_URL)
            if resp.status_code != 200:
                logger.warning(f"HN Top Stories HTTP {resp.status_code}")
                return signals
            story_ids: list[int] = resp.json()
        except Exception as e:
            logger.error(f"HN Top Stories 요청 실패: {e}")
            return signals

        # 2. 상위 N개 스토리 상세 정보 병렬 가져오기
        top_ids = story_ids[:_MAX_STORIES]
        semaphore = asyncio.Semaphore(_CONCURRENT_FETCHES)

        async def fetch_story(story_id: int) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    r = await client.get(_HN_ITEM_URL.format(story_id))
                    if r.status_code == 200:
                        return r.json()
                except Exception as e:
                    logger.debug(f"HN item {story_id} 실패: {e}")
                return None

        tasks = [fetch_story(sid) for sid in top_ids]
        results = await asyncio.gather(*tasks)

        # 3. 결과를 신호로 변환
        for story in results:
            if not story or story.get("type") != "story":
                continue

            title = story.get("title", "")
            url = story.get("url", "")
            score = story.get("score", 0)
            descendants = story.get("descendants", 0)
            by = story.get("by", "")

            # Show HN 등 url이 없는 경우 HN 링크 사용
            if not url:
                url = f"https://news.ycombinator.com/item?id={story.get('id', '')}"

            snippet = f"Score: {score} | Comments: {descendants} | by {by}"

            if title:
                signals.append({
                    "source": SOURCE_NAME,
                    "title": title.strip(),
                    "url": url.strip(),
                    "snippet": snippet,
                    "collected_at": now,
                })

    logger.info(f"Hacker News 크롤링 완료: {len(signals)}건 수집")
    return signals
