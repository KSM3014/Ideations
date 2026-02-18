"""구조화 JSON 로그 — output/logs/{date}.jsonl 에 기록."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import LOG_DIR

KST = timezone(timedelta(hours=9))


def _kst_now() -> datetime:
    return datetime.now(KST)


class _JsonlHandler(logging.Handler):
    """한 줄짜리 JSON 객체를 일별 .jsonl 파일에 추가한다."""

    def __init__(self, log_dir: Path) -> None:
        super().__init__()
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            now = _kst_now()
            entry = {
                "ts": now.isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
            if record.exc_info and record.exc_info[0] is not None:
                entry["exc"] = self.format(record).split("\n")

            # 추가 필드 (extra 딕셔너리)
            for key in ("phase", "batch_id", "duration_sec", "attempt", "trigger"):
                val = getattr(record, key, None)
                if val is not None:
                    entry[key] = val

            daily_path = self._log_dir / f"{now.strftime('%Y-%m-%d')}.jsonl"
            with open(daily_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            self.handleError(record)


def get_logger(name: str, *, level: int = logging.INFO) -> logging.Logger:
    """프로젝트 전역 로거를 반환한다. 콘솔 + JSONL 파일 핸들러."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)

    # 콘솔
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("[%(asctime)s] %(name)s %(levelname)s — %(message)s"))
    logger.addHandler(console)

    # JSONL 파일
    logger.addHandler(_JsonlHandler(LOG_DIR))

    return logger
