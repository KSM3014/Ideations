"""2차 확장 테스트 — 스케줄러: 정각 대기, 카탈로그 갱신 모드 판단."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _loop_runner import _next_hour_wait
from catalog_refresh import determine_mode


class TestNextHourWait:
    def test_next_hour_wait_calculates_correctly(self):
        """_next_hour_wait()는 다음 정각까지 양수 초를 반환해야 한다."""
        wait = _next_hour_wait()
        assert isinstance(wait, float)
        assert wait > 0
        # 최대 3600초(1시간)를 넘을 수 없다
        assert wait <= 3600


class TestCatalogRefreshMode:
    @freeze_time("2026-02-22 03:00:00", tz_offset=9)
    def test_sunday_auto_mode_returns_incremental(self):
        """비-첫째 일요일(2026-02-22, day=22)에는 incremental을 반환한다."""
        mode = determine_mode()
        assert mode == "incremental"

    @freeze_time("2026-02-18 10:00:00", tz_offset=9)
    def test_weekday_auto_mode_returns_skip(self):
        """평일(2026-02-18 수요일)에는 skip을 반환한다."""
        mode = determine_mode()
        assert mode == "skip"
