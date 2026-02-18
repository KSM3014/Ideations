"""카탈로그 갱신 스크립트 — 주간 증분 + 월간 전수.

스케줄:
  - 주간 증분: 매주 일요일 03:00 KST
  - 월간 전수: 첫째 일요일 03:00 KST

사용법:
    python catalog_refresh.py --mode incremental
    python catalog_refresh.py --mode full
    python catalog_refresh.py --auto  # 날짜 기반 자동 판단
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CATALOG_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "catalog-manager" / "scripts"
if str(_CATALOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_CATALOG_SCRIPTS))

from logger import get_logger

logger = get_logger("catalog_refresh")

KST = timezone(timedelta(hours=9))


def _is_first_sunday() -> bool:
    """오늘이 해당 월의 첫째 일요일인지 확인한다."""
    now = datetime.now(KST)
    return now.weekday() == 6 and now.day <= 7


def _is_sunday() -> bool:
    """오늘이 일요일인지 확인한다."""
    return datetime.now(KST).weekday() == 6


def determine_mode() -> str:
    """날짜 기반으로 갱신 모드를 결정한다.

    - 첫째 일요일 → full
    - 기타 일요일 → incremental
    - 평일 → skip
    """
    if _is_first_sunday():
        return "full"
    if _is_sunday():
        return "incremental"
    return "skip"


async def run_incremental() -> dict:
    """증분 스캔 — 최근 변경분만 갱신."""
    logger.info("Starting incremental catalog refresh")

    from catalog_indexer import build_incremental_index
    from catalog_scanner import CatalogScanner

    scanner = CatalogScanner()

    # 증분 스캔
    scan_result = await scanner.scan_incremental()
    logger.info(f"Incremental scan: {scan_result.get('updated', 0)} APIs updated")

    # 인덱스 갱신
    index_result = build_incremental_index()
    logger.info(f"Index updated: {index_result.get('total', 0)} entries")

    return {
        "mode": "incremental",
        "scan": scan_result,
        "index": index_result,
    }


async def run_full() -> dict:
    """전수 스캔 — 전체 카탈로그 재구축."""
    logger.info("Starting full catalog refresh (this may take 2-4 hours)")

    from catalog_indexer import build_full_index, generate_domain_summaries
    from catalog_scanner import CatalogScanner

    scanner = CatalogScanner()

    # 전수 스캔
    scan_result = await scanner.scan_full(max_pages=1200)
    logger.info(f"Full scan: {scan_result.get('total', 0)} APIs cataloged")

    # 전체 인덱스 재생성
    index_result = build_full_index()
    logger.info(f"Full index built: {index_result.get('total', 0)} entries")

    # 도메인 요약 재생성
    summaries = generate_domain_summaries()
    logger.info(f"Domain summaries: {len(summaries)} categories")

    return {
        "mode": "full",
        "scan": scan_result,
        "index": index_result,
        "summaries_count": len(summaries),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="카탈로그 갱신 스크립트")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        help="갱신 모드 (지정하지 않으면 --auto와 동일)",
    )
    parser.add_argument("--auto", action="store_true", help="날짜 기반 자동 판단")
    args = parser.parse_args()

    if args.mode:
        mode = args.mode
    else:
        mode = determine_mode()

    if mode == "skip":
        logger.info("Not a scheduled refresh day — skipping")
        return

    logger.info(f"Catalog refresh mode: {mode}")

    if mode == "incremental":
        result = asyncio.run(run_incremental())
    else:
        result = asyncio.run(run_full())

    logger.info(f"Catalog refresh completed: {result}")


if __name__ == "__main__":
    main()
