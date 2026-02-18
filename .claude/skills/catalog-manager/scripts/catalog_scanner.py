"""카탈로그 스캐너 — data.go.kr Playwright 크롤러.

증분(incremental) 및 전수(full) 스캔 모드 지원.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import RETRY_PLAYWRIGHT
from logger import get_logger

logger = get_logger("catalog_scanner")


class CatalogScanner:
    """data.go.kr Playwright 크롤러."""

    def __init__(self, max_pages: int = 1200) -> None:
        self.max_pages = max_pages
        self.max_retries = RETRY_PLAYWRIGHT["max_retries"]
        self.wait_fixed = RETRY_PLAYWRIGHT["wait_fixed"]

    async def scan_incremental(self, last_scanned_at: str | None = None) -> list[dict[str, Any]]:
        """마지막 스캔 이후 신규/변경 API만 크롤링한다.

        Args:
            last_scanned_at: ISO 형식 타임스탬프. None이면 최근 7일.

        Returns:
            API 메타데이터 딕셔너리 리스트.
        """
        logger.info(f"Incremental scan starting (since {last_scanned_at})")
        # Stage 1에서 Playwright 로직 구현 예정
        # 현재는 빈 리스트 반환 (스텁)
        return []

    async def scan_full(self) -> list[dict[str, Any]]:
        """전수 스캔 — 최대 max_pages 페이지까지.

        Returns:
            API 메타데이터 딕셔너리 리스트.
        """
        logger.info(f"Full scan starting (max_pages={self.max_pages})")
        # Stage 1에서 Playwright 로직 구현 예정
        return []

    async def _crawl_page(self, page_num: int) -> list[dict[str, Any]]:
        """단일 페이지 크롤링 (Playwright).

        Stage 1에서 구현 예정.
        """
        return []
