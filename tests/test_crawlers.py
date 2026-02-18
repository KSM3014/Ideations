"""MVP 게이트 테스트 — 신호 수집기: 전체 실패 → 빈 리스트, URL 캐시, 라운드로빈 회전."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SIGNAL_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "signal-collector" / "scripts"
if str(_SIGNAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SIGNAL_SCRIPTS))

from signal_aggregator import (
    URLCache,
    _pick_rotation_sources,
    collect_signals,
    reset_rotation_index,
)

KST = timezone(timedelta(hours=9))


# ──────────────────────────── Fixtures ────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rotation():
    """각 테스트 전에 라운드로빈 인덱스를 초기화한다."""
    reset_rotation_index()
    yield
    reset_rotation_index()


@pytest.fixture
def url_cache(tmp_path: Path):
    """임시 파일 기반 URLCache 인스턴스."""
    cache_path = tmp_path / "test_signal_cache.json"
    return URLCache(cache_path=cache_path, ttl_hours=24)


# ──────────────────────────── 테스트: 모든 소스 실패 → 빈 리스트 ────────────────────────────


class TestAllSourcesFail:
    """모든 크롤러가 실패해도 빈 리스트를 반환한다 (graceful failure)."""

    @pytest.mark.asyncio
    async def test_all_sources_fail_returns_empty(self, tmp_path: Path):
        """모든 소스가 예외를 발생시켜도 collect_signals()는 빈 리스트를 반환한다."""
        cache = URLCache(cache_path=tmp_path / "cache.json", ttl_hours=24)

        # _run_crawler가 항상 빈 리스트를 반환하도록 패치 (내부 예외 처리 시뮬레이션)
        async def _empty_crawler(source_name, timeout_sec):
            return []

        with patch("signal_aggregator._run_crawler", side_effect=_empty_crawler):
            result = await collect_signals(
                always_sources=["google_trends"],
                rotation_pool=["news", "tech", "policy", "funding"],
                rotation_pick=2,
                timeout_sec=5,
                cache=cache,
            )

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self, tmp_path: Path):
        """소스가 타임아웃되어도 빈 리스트를 반환한다."""
        cache = URLCache(cache_path=tmp_path / "cache.json", ttl_hours=24)

        # _run_crawler는 내부에서 타임아웃을 처리하고 빈 리스트를 반환
        async def _timeout_crawler(source_name, timeout_sec):
            return []

        with patch("signal_aggregator._run_crawler", side_effect=_timeout_crawler):
            result = await collect_signals(
                always_sources=["google_trends"],
                rotation_pool=["news", "tech"],
                rotation_pick=1,
                timeout_sec=1,
                cache=cache,
            )

        assert result == []


# ──────────────────────────── 테스트: URL 캐시 중복 방지 ────────────────────────────


class TestURLCache:
    """24시간 URL 캐시가 중복 크롤링을 방지한다."""

    def test_add_and_check_cached(self, url_cache: URLCache):
        """캐시에 추가한 URL은 is_cached=True."""
        url_cache.add("https://example.com/article-1")
        assert url_cache.is_cached("https://example.com/article-1") is True

    def test_uncached_url_returns_false(self, url_cache: URLCache):
        """캐시에 없는 URL은 is_cached=False."""
        assert url_cache.is_cached("https://example.com/never-seen") is False

    def test_expired_url_not_cached(self, tmp_path: Path):
        """TTL 만료된 URL은 캐시에서 제거된다."""
        cache_path = tmp_path / "expired_cache.json"

        # 25시간 전 타임스탬프를 직접 작성
        old_ts = (datetime.now(KST) - timedelta(hours=25)).isoformat()
        cache_data = {"https://example.com/old": old_ts}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

        cache = URLCache(cache_path=cache_path, ttl_hours=24)
        assert cache.is_cached("https://example.com/old") is False

    def test_recent_url_still_cached(self, tmp_path: Path):
        """TTL 이내의 URL은 캐시에 남아있다."""
        cache_path = tmp_path / "recent_cache.json"

        recent_ts = (datetime.now(KST) - timedelta(hours=1)).isoformat()
        cache_data = {"https://example.com/recent": recent_ts}
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f)

        cache = URLCache(cache_path=cache_path, ttl_hours=24)
        assert cache.is_cached("https://example.com/recent") is True

    def test_save_and_reload(self, tmp_path: Path):
        """캐시를 저장 후 재로드하면 데이터가 유지된다."""
        cache_path = tmp_path / "persist_cache.json"

        cache1 = URLCache(cache_path=cache_path, ttl_hours=24)
        cache1.add("https://example.com/persist")
        cache1.save()

        cache2 = URLCache(cache_path=cache_path, ttl_hours=24)
        assert cache2.is_cached("https://example.com/persist") is True

    @pytest.mark.asyncio
    async def test_cached_urls_filtered_from_signals(self, tmp_path: Path):
        """이미 캐시된 URL의 신호는 결과에서 제외된다."""
        cache = URLCache(cache_path=tmp_path / "filter_cache.json", ttl_hours=24)
        cache.add("https://example.com/already-seen")

        fake_signals = [
            {
                "source": "google_trends",
                "title": "이미 본 기사",
                "url": "https://example.com/already-seen",
                "snippet": "중복",
                "collected_at": datetime.now(KST).isoformat(),
            },
            {
                "source": "google_trends",
                "title": "새 기사",
                "url": "https://example.com/new-article",
                "snippet": "신규",
                "collected_at": datetime.now(KST).isoformat(),
            },
        ]

        async def _mock_crawler(source_name, timeout_sec):
            return fake_signals

        with patch("signal_aggregator._run_crawler", side_effect=_mock_crawler):
            result = await collect_signals(
                always_sources=["google_trends"],
                rotation_pool=[],
                rotation_pick=0,
                timeout_sec=30,
                cache=cache,
            )

        urls = [s["url"] for s in result]
        assert "https://example.com/already-seen" not in urls
        assert "https://example.com/new-article" in urls


# ──────────────────────────── 테스트: 라운드로빈 회전 ────────────────────────────


class TestRotation:
    """라운드로빈 회전이 정확히 2개를 선택하고 순환한다."""

    def test_picks_exactly_2_from_pool(self):
        """풀에서 정확히 2개를 선택한다."""
        pool = ["news", "tech", "policy", "funding"]
        selected = _pick_rotation_sources(pool, 2)
        assert len(selected) == 2
        assert all(s in pool for s in selected)

    def test_rotation_cycles_through_pool(self):
        """연속 호출 시 라운드로빈으로 순환한다."""
        pool = ["news", "tech", "policy", "funding"]

        # 첫 번째 호출: news, tech
        batch1 = _pick_rotation_sources(pool, 2)
        assert batch1 == ["news", "tech"]

        # 두 번째 호출: policy, funding
        batch2 = _pick_rotation_sources(pool, 2)
        assert batch2 == ["policy", "funding"]

        # 세 번째 호출: 다시 news, tech (순환)
        batch3 = _pick_rotation_sources(pool, 2)
        assert batch3 == ["news", "tech"]

    def test_no_duplicates_in_single_pick(self):
        """한 번의 선택에서 중복이 없다."""
        pool = ["news", "tech", "policy", "funding"]
        selected = _pick_rotation_sources(pool, 2)
        assert len(selected) == len(set(selected))

    def test_empty_pool_returns_empty(self):
        """빈 풀에서는 빈 리스트를 반환한다."""
        assert _pick_rotation_sources([], 2) == []

    def test_pick_zero_returns_empty(self):
        """pick=0이면 빈 리스트를 반환한다."""
        assert _pick_rotation_sources(["news", "tech"], 0) == []

    @pytest.mark.asyncio
    async def test_collect_signals_uses_rotation(self, tmp_path: Path):
        """collect_signals가 always + 라운드로빈 선택을 사용한다."""
        cache = URLCache(cache_path=tmp_path / "rotation_cache.json", ttl_hours=24)
        called_sources: list[str] = []

        async def _tracking_crawler(source_name, timeout_sec):
            called_sources.append(source_name)
            return []

        with patch("signal_aggregator._run_crawler", side_effect=_tracking_crawler):
            await collect_signals(
                always_sources=["google_trends"],
                rotation_pool=["news", "tech", "policy", "funding"],
                rotation_pick=2,
                timeout_sec=30,
                cache=cache,
            )

        # google_trends는 항상 포함
        assert "google_trends" in called_sources
        # 총 3개 소스 (always 1 + rotation 2)
        assert len(called_sources) == 3
        # 라운드로빈에서 선택된 2개는 풀에 포함
        rotated = [s for s in called_sources if s != "google_trends"]
        assert len(rotated) == 2
        assert all(s in ["news", "tech", "policy", "funding"] for s in rotated)
