"""MVP Gate 테스트 — 동시성 제어 (최대 2 병렬, 3번째 거부)."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SCRIPTS = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _loop_runner import RunLock


class TestRunLock:
    """MVP Gate #14: 동시성 제어 (최대 2 병렬, 3번째 거부)."""

    def test_first_acquire_succeeds(self, tmp_path):
        lock = RunLock(lock_dir=tmp_path / "locks", max_concurrent=2)
        assert lock.acquire() is True
        lock.release()

    def test_two_concurrent_succeed(self, tmp_path):
        lock_dir = tmp_path / "locks"
        lock1 = RunLock(lock_dir=lock_dir, max_concurrent=2)
        lock2 = RunLock(lock_dir=lock_dir, max_concurrent=2)

        assert lock1.acquire() is True
        assert lock2.acquire() is True

        lock1.release()
        lock2.release()

    def test_third_concurrent_rejected(self, tmp_path):
        lock_dir = tmp_path / "locks"
        lock1 = RunLock(lock_dir=lock_dir, max_concurrent=2)
        lock2 = RunLock(lock_dir=lock_dir, max_concurrent=2)
        lock3 = RunLock(lock_dir=lock_dir, max_concurrent=2)

        assert lock1.acquire() is True
        assert lock2.acquire() is True
        # 3번째는 거부되어야 함
        assert lock3.acquire() is False

        lock1.release()
        lock2.release()

    def test_release_frees_slot(self, tmp_path):
        lock_dir = tmp_path / "locks"
        lock1 = RunLock(lock_dir=lock_dir, max_concurrent=1)
        lock2 = RunLock(lock_dir=lock_dir, max_concurrent=1)

        assert lock1.acquire() is True
        assert lock2.acquire() is False

        lock1.release()
        # 슬롯이 해제되었으므로 다시 성공
        assert lock2.acquire() is True
        lock2.release()

    def test_max_concurrent_one(self, tmp_path):
        lock_dir = tmp_path / "locks"
        lock1 = RunLock(lock_dir=lock_dir, max_concurrent=1)
        lock2 = RunLock(lock_dir=lock_dir, max_concurrent=1)

        assert lock1.acquire() is True
        assert lock2.acquire() is False

        lock1.release()

    def test_release_without_acquire_safe(self, tmp_path):
        lock = RunLock(lock_dir=tmp_path / "locks", max_concurrent=2)
        # release 호출해도 에러 없어야 함
        lock.release()

    def test_lock_dir_created(self, tmp_path):
        lock_dir = tmp_path / "new_locks"
        assert not lock_dir.exists()
        lock = RunLock(lock_dir=lock_dir, max_concurrent=2)
        assert lock_dir.exists()

    def test_multiple_release_safe(self, tmp_path):
        lock = RunLock(lock_dir=tmp_path / "locks", max_concurrent=2)
        assert lock.acquire() is True
        lock.release()
        lock.release()  # 두 번째 release도 안전해야 함
