"""대시보드 배치 기록 — dashboard_batches.jsonl 원자적 추가."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import DASHBOARD_BATCHES_PATH
from logger import get_logger
from utils import append_jsonl, kst_now

logger = get_logger("dashboard_writer")


class DashboardWriter:
    """대시보드 배치를 JSONL에 기록한다."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DASHBOARD_BATCHES_PATH

    def write_batch(self, batch_id: str, ideas: list[dict[str, Any]]) -> bool:
        """배치를 dashboard_batches.jsonl에 추가한다.

        Returns:
            성공 여부.
        """
        record = {
            "schema_version": "1.0",
            "batch_id": batch_id,
            "timestamp": kst_now().isoformat(),
            "ideas": ideas,
        }
        try:
            append_jsonl(self.path, record)
            logger.info(f"Dashboard batch written: {batch_id} ({len(ideas)} ideas)")
            return True
        except Exception as e:
            logger.error(f"Dashboard write failed: {e}")
            return False
