"""아카이브 관리자 — ideas_archive.jsonl 관리."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import IDEAS_ARCHIVE_PATH
from logger import get_logger
from utils import append_jsonl, kst_now, read_jsonl

logger = get_logger("archive_manager")


class ArchiveManager:
    """아이디어 아카이브를 관리한다."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else IDEAS_ARCHIVE_PATH

    def archive_ideas(self, batch_id: str, ideas: list[dict[str, Any]]) -> int:
        """아이디어를 아카이브에 추가한다.

        Returns:
            추가된 아이디어 수.
        """
        count = 0
        for idea in ideas:
            record = {
                "batch_id": batch_id,
                "archived_at": kst_now().isoformat(),
                **idea,
            }
            append_jsonl(self.path, record)
            count += 1

        logger.info(f"Archived {count} ideas from batch {batch_id}")
        return count

    def get_recent(self, hours: int = 24) -> list[dict]:
        """최근 N시간 이내의 아카이브를 반환한다."""
        from datetime import timedelta

        cutoff = kst_now() - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        all_records = read_jsonl(self.path)
        recent = [r for r in all_records if r.get("archived_at", "") >= cutoff_str]
        return recent

    def get_service_names(self, hours: int = 24) -> list[str]:
        """최근 N시간 서비스명 목록 (중복 회피용)."""
        recent = self.get_recent(hours)
        return [r.get("service_name", "") for r in recent if r.get("service_name")]
