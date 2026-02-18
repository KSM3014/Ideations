"""시스템 헬스 API — GET /api/health."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter

from config import DASHBOARD_BATCHES_PATH
from utils import read_jsonl

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """시스템 상태를 반환한다."""
    from server.app import get_uptime

    batches = read_jsonl(DASHBOARD_BATCHES_PATH)
    last_batch = batches[-1] if batches else None

    return {
        "status": "ok",
        "last_batch_id": last_batch.get("batch_id") if last_batch else None,
        "last_run_at": last_batch.get("timestamp") if last_batch else None,
        "uptime_sec": get_uptime(),
    }
