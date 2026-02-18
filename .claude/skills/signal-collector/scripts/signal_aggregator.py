"""신호 수집 어그리게이터 — 라운드로빈 소스 선택, URL 캐시, 타임아웃 관리.

동작 방식:
    1. Google Trends KR 크롤러는 항상 실행 (SIGNAL_ROTATION_ALWAYS)
    2. 나머지 4개 소스 중 2개를 라운드로빈으로 선택 (SIGNAL_ROTATION_POOL)
    3. 24시간 URL 캐시로 중복 크롤링 방지
    4. 소스별 3분 타임아웃 (SIGNAL_SOURCE_TIMEOUT_SEC)
    5. 모든 소스 실패 시 빈 리스트 반환 (Phase 2는 빈 입력으로 계속 진행)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import (
    SIGNAL_CACHE_PATH,
    SIGNAL_ROTATION_ALWAYS,
    SIGNAL_ROTATION_PICK,
    SIGNAL_ROTATION_POOL,
    SIGNAL_SOURCE_TIMEOUT_SEC,
    SIGNAL_URL_CACHE_TTL_HOURS,
)
from logger import get_logger

logger = get_logger("signal_aggregator")

KST = timezone(timedelta(hours=9))

# ──────────────────────────── 크롤러 레지스트리 ────────────────────────────

_CRAWLER_MODULES: dict[str, str] = {
    "google_trends": "crawl_trends",
    "news": "crawl_news",
    "tech": "crawl_tech",
    "policy": "crawl_policy",
    "funding": "crawl_funding",
}

# ──────────────────────────── 라운드로빈 상태 ────────────────────────────

_rotation_index: int = 0


def _pick_rotation_sources(pool: list[str], pick: int) -> list[str]:
    """라운드로빈으로 pool에서 pick개를 선택한다.

    매 호출마다 인덱스를 전진시켜 순환한다.
    """
    global _rotation_index
    if not pool or pick <= 0:
        return []

    selected: list[str] = []
    for i in range(pick):
        idx = (_rotation_index + i) % len(pool)
        selected.append(pool[idx])
    _rotation_index = (_rotation_index + pick) % len(pool)

    return selected


def get_rotation_index() -> int:
    """현재 라운드로빈 인덱스를 반환한다 (테스트용)."""
    return _rotation_index


def reset_rotation_index() -> None:
    """라운드로빈 인덱스를 초기화한다 (테스트용)."""
    global _rotation_index
    _rotation_index = 0


# ──────────────────────────── URL 캐시 ────────────────────────────


class URLCache:
    """24시간 TTL URL 캐시 — 중복 크롤링 방지.

    캐시 파일: data/signal_cache.json
    구조: {"url": "ISO-8601-timestamp", ...}
    """

    def __init__(self, cache_path: Path | None = None, ttl_hours: int | None = None) -> None:
        self.cache_path = cache_path or SIGNAL_CACHE_PATH
        self.ttl_hours = ttl_hours if ttl_hours is not None else SIGNAL_URL_CACHE_TTL_HOURS
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """캐시 파일을 로드한다."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 신규 포맷: {"schema_version": ..., "cached_urls": {...}}
                if isinstance(data, dict) and "cached_urls" in data:
                    self._cache = data["cached_urls"]
                else:
                    self._cache = data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"URL 캐시 로드 실패, 초기화: {e}")
                self._cache = {}
        self._evict_expired()

    def _save(self) -> None:
        """캐시를 파일에 저장한다."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": "1.0",
            "cached_urls": self._cache,
            "last_rotation_index": 0,
        }
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _evict_expired(self) -> None:
        """TTL이 만료된 항목을 제거한다."""
        now = datetime.now(KST)
        cutoff = now - timedelta(hours=self.ttl_hours)
        expired = [
            url
            for url, ts in self._cache.items()
            if datetime.fromisoformat(ts) < cutoff
        ]
        for url in expired:
            del self._cache[url]
        if expired:
            logger.info(f"URL 캐시: {len(expired)}건 만료 제거")

    def is_cached(self, url: str) -> bool:
        """URL이 캐시에 있는지 확인한다."""
        if url not in self._cache:
            return False
        ts = datetime.fromisoformat(self._cache[url])
        now = datetime.now(KST)
        if (now - ts) > timedelta(hours=self.ttl_hours):
            del self._cache[url]
            return False
        return True

    def add(self, url: str) -> None:
        """URL을 캐시에 추가한다."""
        self._cache[url] = datetime.now(KST).isoformat()

    def save(self) -> None:
        """캐시를 디스크에 저장한다."""
        self._evict_expired()
        self._save()

    @property
    def size(self) -> int:
        return len(self._cache)


# ──────────────────────────── 크롤러 실행 ────────────────────────────


async def _run_crawler(source_name: str, timeout_sec: int) -> list[dict[str, Any]]:
    """개별 크롤러를 타임아웃과 함께 실행한다.

    실패 시 빈 리스트를 반환한다 (graceful failure).
    """
    module_name = _CRAWLER_MODULES.get(source_name)
    if not module_name:
        logger.error(f"알 수 없는 소스: {source_name}")
        return []

    try:
        # 동적 임포트
        import importlib

        _scripts_dir = Path(__file__).resolve().parent
        if str(_scripts_dir) not in sys.path:
            sys.path.insert(0, str(_scripts_dir))
        module = importlib.import_module(module_name)

        # 타임아웃 적용
        signals = await asyncio.wait_for(module.crawl(), timeout=timeout_sec)
        logger.info(f"[{source_name}] 크롤링 성공: {len(signals)}건")
        return signals

    except asyncio.TimeoutError:
        logger.warning(f"[{source_name}] 타임아웃 ({timeout_sec}초 초과)")
        return []
    except Exception as e:
        logger.error(f"[{source_name}] 크롤링 실패: {e}", exc_info=True)
        return []


def _filter_cached(signals: list[dict[str, Any]], cache: URLCache) -> list[dict[str, Any]]:
    """캐시에 이미 있는 URL을 제외한다."""
    new_signals: list[dict[str, Any]] = []
    for sig in signals:
        url = sig.get("url", "")
        if url and cache.is_cached(url):
            logger.debug(f"캐시 히트, 스킵: {url}")
            continue
        if url:
            cache.add(url)
        new_signals.append(sig)
    return new_signals


# ──────────────────────────── 메인 어그리게이터 ────────────────────────────


async def collect_signals(
    *,
    always_sources: list[str] | None = None,
    rotation_pool: list[str] | None = None,
    rotation_pick: int | None = None,
    timeout_sec: int | None = None,
    cache: URLCache | None = None,
) -> list[dict[str, Any]]:
    """신호를 수집한다.

    1. always_sources(기본: google_trends)는 항상 실행
    2. rotation_pool(기본: news, tech, policy, funding) 중 rotation_pick(기본: 2)개 선택
    3. 각 소스를 병렬 실행, 소스별 타임아웃 적용
    4. URL 캐시로 중복 제거
    5. 모든 소스 실패 시 빈 리스트 반환

    Returns:
        list[dict]: 수집된 신호 목록
    """
    _always = always_sources if always_sources is not None else SIGNAL_ROTATION_ALWAYS
    _pool = rotation_pool if rotation_pool is not None else SIGNAL_ROTATION_POOL
    _pick = rotation_pick if rotation_pick is not None else SIGNAL_ROTATION_PICK
    _timeout = timeout_sec if timeout_sec is not None else SIGNAL_SOURCE_TIMEOUT_SEC

    # 라운드로빈으로 소스 선택
    selected_from_pool = _pick_rotation_sources(_pool, _pick)
    active_sources = list(_always) + selected_from_pool

    logger.info(
        f"신호 수집 시작: always={_always}, "
        f"rotation_selected={selected_from_pool}, "
        f"timeout={_timeout}s"
    )

    # URL 캐시 초기화
    url_cache = cache if cache is not None else URLCache()

    # 병렬 크롤링
    tasks = [_run_crawler(src, _timeout) for src in active_sources]
    results = await asyncio.gather(*tasks)

    # 결과 통합 + 캐시 필터링
    all_signals: list[dict[str, Any]] = []
    for source_signals in results:
        filtered = _filter_cached(source_signals, url_cache)
        all_signals.extend(filtered)

    # 캐시 저장
    try:
        url_cache.save()
    except OSError as e:
        logger.warning(f"URL 캐시 저장 실패: {e}")

    logger.info(f"신호 수집 완료: 총 {len(all_signals)}건 (소스 {len(active_sources)}개)")
    return all_signals
