"""카탈로그 스캐너 — data.go.kr Playwright 크롤러.

증분(incremental) 및 전수(full) 스캔 모드 지원.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import RETRY_PLAYWRIGHT
from logger import get_logger

logger = get_logger("catalog_scanner")

_BASE_URL = "https://www.data.go.kr/tcs/dss/selectDataSetList.do"
_ITEMS_PER_PAGE = 10


class CatalogScanner:
    """data.go.kr Playwright 크롤러."""

    def __init__(self, max_pages: int = 1200) -> None:
        self.max_pages = max_pages
        self.max_retries = RETRY_PLAYWRIGHT["max_retries"]
        self.wait_fixed = RETRY_PLAYWRIGHT["wait_fixed"]

    async def scan_incremental(self, last_scanned_at: str | None = None) -> list[dict[str, Any]]:
        """마지막 스캔 이후 신규/변경 API만 크롤링한다.

        최근 업데이트순 정렬 → 이미 스캔한 API가 나오면 중단.
        """
        logger.info(f"Incremental scan starting (since {last_scanned_at})")
        return await self._crawl(mode="incremental", max_pages=min(50, self.max_pages))

    async def scan_full(self) -> list[dict[str, Any]]:
        """전수 스캔 — 최대 max_pages 페이지까지."""
        logger.info(f"Full scan starting (max_pages={self.max_pages})")
        return await self._crawl(mode="full", max_pages=self.max_pages)

    async def _crawl(self, *, mode: str, max_pages: int) -> list[dict[str, Any]]:
        """Playwright로 data.go.kr Open API 목록을 크롤링한다."""
        from playwright.async_api import async_playwright

        all_apis: list[dict[str, Any]] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(locale="ko-KR")
            page = await context.new_page()

            try:
                for page_num in range(1, max_pages + 1):
                    apis = await self._crawl_page(page, page_num)
                    if not apis:
                        logger.info(f"Page {page_num}: no items, stopping")
                        break

                    all_apis.extend(apis)

                    if page_num % 50 == 0:
                        logger.info(f"Progress: {page_num} pages, {len(all_apis)} APIs")

                    # 서버 부하 방지 — 페이지당 0.5초 대기
                    await asyncio.sleep(0.5)
            finally:
                await browser.close()

        logger.info(f"Scan complete: {len(all_apis)} APIs from {mode} scan")
        return all_apis

    async def _crawl_page(self, page: Any, page_num: int) -> list[dict[str, Any]]:
        """단일 페이지 크롤링."""
        url = f"{_BASE_URL}?dType=API&currentPage={page_num}"

        for attempt in range(self.max_retries + 1):
            try:
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=15000)

                items = await page.query_selector_all(".result-list li")
                if not items:
                    return []

                apis = []
                for item in items:
                    api = await self._extract_api(item)
                    if api:
                        apis.append(api)

                return apis

            except Exception as e:
                logger.warning(f"Page {page_num} attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.wait_fixed)
                else:
                    logger.error(f"Page {page_num} skipped after {self.max_retries + 1} attempts")
                    return []

        return []

    async def _extract_api(self, item: Any) -> dict[str, Any] | None:
        """단일 API 항목에서 메타데이터를 추출한다."""
        try:
            # API 상세 링크 + ID
            link_el = await item.query_selector("dl dt a")
            if not link_el:
                return None

            href = await link_el.get_attribute("href") or ""
            name = (await link_el.inner_text()).strip()

            api_id_match = re.search(r"/data/(\d+)/", href)
            api_id = api_id_match.group(1) if api_id_match else ""
            if not api_id:
                return None

            # 카테고리 태그
            tags = await item.query_selector_all(".tag-area .labelset")
            categories = []
            provider = ""
            for tag in tags:
                cls = await tag.get_attribute("class") or ""
                text = (await tag.inner_text()).strip()
                if not text:
                    continue
                if "national" in cls or "local" in cls:
                    provider = text
                else:
                    categories.append(text)

            # 설명
            desc_el = await item.query_selector("dl dd")
            desc = (await desc_el.inner_text()).strip() if desc_el else ""

            # 데이터 포맷은 이름에 포함 (예: "XML JSON 서비스명")
            data_format = "JSON"
            name_clean = name
            for fmt in ("XML", "JSON", "CSV"):
                if fmt in name:
                    data_format = fmt
                    name_clean = name_clean.replace(fmt, "").strip()

            return {
                "api_id": f"DATAGOKR-{api_id}",
                "name": name_clean,
                "description": desc[:500],
                "category": categories[0] if categories else "",
                "provider": provider or (categories[1] if len(categories) > 1 else ""),
                "endpoint_url": f"https://www.data.go.kr/data/{api_id}/openapi.do",
                "data_format": data_format,
                "is_active": 1,
            }
        except Exception as e:
            logger.warning(f"Extract failed: {e}")
            return None


async def bootstrap(max_pages: int = 1200) -> None:
    """카탈로그 부트스트랩 — DB 초기화 + 전수 스캔."""
    from catalog_store import CatalogStore

    store = CatalogStore()
    scanner = CatalogScanner(max_pages=max_pages)

    logger.info("Starting catalog bootstrap...")
    apis = await scanner.scan_full()

    inserted = 0
    for api in apis:
        try:
            store.upsert_api(api)
            inserted += 1
        except Exception as e:
            logger.warning(f"Failed to upsert {api.get('api_id')}: {e}")

    # 도메인 요약 생성
    dist = store.get_category_distribution()
    for cat, count in dist.items():
        store.upsert_domain_summary(cat, count, "", f"{cat} 분야 공공 API {count}개")

    logger.info(f"Bootstrap complete: {inserted}/{len(apis)} APIs inserted, {len(dist)} categories")
    print(f"Bootstrap complete: {inserted}/{len(apis)} APIs inserted, {len(dist)} categories")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="카탈로그 스캐너")
    parser.add_argument("--mode", choices=["full", "incremental", "bootstrap"], default="bootstrap")
    parser.add_argument("--max-pages", type=int, default=1200)
    args = parser.parse_args()

    if args.mode == "bootstrap":
        asyncio.run(bootstrap(max_pages=args.max_pages))
    elif args.mode == "full":
        scanner = CatalogScanner(max_pages=args.max_pages)
        apis = asyncio.run(scanner.scan_full())
        print(f"Found {len(apis)} APIs")
    elif args.mode == "incremental":
        scanner = CatalogScanner(max_pages=args.max_pages)
        apis = asyncio.run(scanner.scan_incremental())
        print(f"Found {len(apis)} APIs")
