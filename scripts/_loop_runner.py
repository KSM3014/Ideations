"""매시 정각 루프 러너 — 동시성 제어(최대 2 병렬), 락 파일.

사용법:
    python _loop_runner.py
    python _loop_runner.py --once   # 1회만 실행
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import PROJECT_ROOT
from logger import get_logger

logger = get_logger("loop_runner")

LOCK_DIR = PROJECT_ROOT / "output" / "locks"
MAX_CONCURRENT = 2

# Windows용 파일 락
if sys.platform == "win32":
    import msvcrt

    def _lock_file(fd):
        msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_file(fd):
        try:
            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
else:
    import fcntl

    def _lock_file(fd):
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_file(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


class RunLock:
    """파일 기반 동시성 제어. 최대 MAX_CONCURRENT개만 동시 실행 허용."""

    def __init__(self, lock_dir: Path = LOCK_DIR, max_concurrent: int = MAX_CONCURRENT) -> None:
        self.lock_dir = lock_dir
        self.max_concurrent = max_concurrent
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._lock_file = None
        self._lock_fd = None

    def acquire(self) -> bool:
        """락을 획득한다. 성공하면 True, 슬롯 부족이면 False."""
        for slot in range(self.max_concurrent):
            lock_path = self.lock_dir / f"run_slot_{slot}.lock"
            try:
                fd = open(lock_path, "w")
                _lock_file(fd)
                fd.write(f"{os.getpid()}\n{datetime.utcnow().isoformat()}\n")
                fd.flush()
                self._lock_file = lock_path
                self._lock_fd = fd
                logger.info(f"Lock acquired: slot {slot}")
                return True
            except (IOError, OSError):
                try:
                    fd.close()
                except Exception:
                    pass
                continue

        logger.warning(f"All {self.max_concurrent} slots occupied — run rejected")
        return False

    def release(self) -> None:
        """락을 해제한다."""
        if self._lock_fd:
            try:
                _unlock_file(self._lock_fd)
                self._lock_fd.close()
            except Exception:
                pass
            self._lock_fd = None
            self._lock_file = None
            logger.info("Lock released")


def _next_hour_wait() -> float:
    """다음 정각까지 대기 시간(초)을 반환한다."""
    now = datetime.utcnow()
    next_hour = now.replace(minute=0, second=0, microsecond=0)
    if next_hour <= now:
        next_hour += timedelta(hours=1)
    return (next_hour - now).total_seconds()


def run_once() -> bool:
    """파이프라인을 1회 실행한다. 락 획득 실패 시 False."""
    lock = RunLock()
    if not lock.acquire():
        return False

    try:
        from scripts.run_engine import IdeationEngine

        engine = IdeationEngine()
        result = engine.run()
        logger.info(f"Pipeline completed: success={result.get('success')}")
        return result.get("success", False)
    except Exception as e:
        logger.error(f"Pipeline run failed: {e}", exc_info=True)
        return False
    finally:
        lock.release()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="매시 정각 루프 러너")
    parser.add_argument("--once", action="store_true", help="1회만 실행")
    args = parser.parse_args()

    if args.once:
        success = run_once()
        sys.exit(0 if success else 1)

    logger.info("Loop runner started — Ctrl+C to stop")
    while True:
        success = run_once()
        wait = _next_hour_wait()
        logger.info(f"Next run in {wait:.0f}s")
        time.sleep(wait)


if __name__ == "__main__":
    main()
