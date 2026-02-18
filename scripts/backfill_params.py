"""카탈로그 파라미터 백필 — 상세 페이지 크롤링으로 파라미터/오퍼레이션 수집.

사용법:
    python scripts/backfill_params.py --limit 50    # 처음 50개만
    python scripts/backfill_params.py --all          # 전체 (시간 소요)
    python scripts/backfill_params.py --missing-only  # 파라미터 없는 것만
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CATALOG_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "catalog-manager" / "scripts"
if str(_CATALOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_CATALOG_SCRIPTS))

from catalog_scanner import CatalogScanner
from catalog_store import CatalogStore
from logger import get_logger

logger = get_logger("backfill_params")


async def backfill(
    *, limit: int | None = None, missing_only: bool = True, delay: float = 1.5
) -> dict[str, int]:
    """파라미터가 없는 API의 상세 페이지를 크롤링하여 파라미터를 수집한다."""
    store = CatalogStore()
    scanner = CatalogScanner()

    apis = store.list_apis(active_only=True)
    logger.info(f"Total active APIs: {len(apis)}")

    # 파라미터 없는 API만 필터링
    if missing_only:
        targets = []
        for api in apis:
            params = store.get_parameters(api["api_id"])
            if not params:
                targets.append(api["api_id"])
        logger.info(f"APIs missing parameters: {len(targets)}")
    else:
        targets = [a["api_id"] for a in apis]

    if limit:
        targets = targets[:limit]

    logger.info(f"Backfilling {len(targets)} APIs (delay={delay}s)")

    stats = {"total": len(targets), "success": 0, "params_added": 0, "ops_added": 0, "failed": 0}

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="ko-KR")
        page = await context.new_page()

        try:
            for i, api_id in enumerate(targets):
                raw_id = api_id.replace("DATAGOKR-", "")
                url = f"https://www.data.go.kr/data/{raw_id}/openapi.do"

                try:
                    await page.goto(url, timeout=30000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    # Swagger UI 비동기 렌더링 대기
                    try:
                        await page.wait_for_selector(
                            ".opblock-summary-control, .opblock-summary, .opblock",
                            timeout=10000,
                        )
                    except Exception:
                        logger.debug(f"[{i+1}] {api_id}: Swagger UI not found, skipping params")

                    params = await scanner._extract_params(page)
                    ops = await scanner._extract_operations(page)

                    if params:
                        store.upsert_parameters(api_id, params)
                        stats["params_added"] += len(params)
                    if ops:
                        store.upsert_operations(api_id, ops)
                        stats["ops_added"] += len(ops)

                    stats["success"] += 1

                except Exception as e:
                    logger.warning(f"[{i+1}/{len(targets)}] {api_id} failed: {e}")
                    stats["failed"] += 1

                if (i + 1) % 20 == 0:
                    logger.info(
                        f"Progress: {i+1}/{len(targets)} "
                        f"(success={stats['success']}, params={stats['params_added']}, failed={stats['failed']})"
                    )

                await asyncio.sleep(delay)
        finally:
            await browser.close()

    logger.info(f"Backfill complete: {stats}")
    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="카탈로그 파라미터 백필")
    parser.add_argument("--limit", type=int, default=None, help="처리할 API 수 제한")
    parser.add_argument("--all", action="store_true", help="전체 API 백필")
    parser.add_argument("--missing-only", action="store_true", default=True, help="파라미터 없는 것만")
    parser.add_argument("--delay", type=float, default=1.5, help="API간 대기 시간(초)")
    args = parser.parse_args()

    if args.all:
        args.missing_only = False

    stats = asyncio.run(backfill(
        limit=args.limit,
        missing_only=args.missing_only,
        delay=args.delay,
    ))
    print(f"\nResults: {stats}")


if __name__ == "__main__":
    main()
