"""ProductHunt / Hacker News 크롤러 — Playwright 기반 스텁.

ProductHunt 오늘의 제품과 HN 프론트페이지를 수집한다.
Phase 2에서 실제 Playwright 로직으로 채운다.
"""

from __future__ import annotations

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


async def crawl() -> list[dict[str, Any]]:
    """ProductHunt 오늘의 제품 + Hacker News 프론트페이지를 수집한다.

    Returns:
        list[dict]: 각 항목은 아래 키를 가진다:
            - source: str  — 소스 식별자 ("tech")
            - title: str   — 제품/게시물 제목
            - url: str     — 상세 URL
            - snippet: str — 제품 태그라인 또는 게시물 요약
            - collected_at: str — ISO 8601 수집 시각 (KST)
    """
    logger.info(
        f"ProductHunt/HN 크롤링 시작 "
        f"(timeout={SIGNAL_SOURCE_TIMEOUT_SEC}s, retry={RETRY_PLAYWRIGHT})"
    )

    signals: list[dict[str, Any]] = []

    # ── TODO (Phase 2): Playwright 크롤링 로직 구현 ──
    # 1. Playwright 브라우저 시작 (headless)
    # 2. ProductHunt: https://www.producthunt.com/ 접속 → 오늘의 제품 파싱
    # 3. Hacker News: https://news.ycombinator.com/ 접속 → 프론트페이지 파싱
    # 4. source_config.json의 CSS 셀렉터로 항목 파싱
    # 5. 각 항목을 signals 리스트에 추가
    # 6. 브라우저 정리

    logger.info(f"ProductHunt/HN 크롤링 완료: {len(signals)}건 수집")
    return signals
