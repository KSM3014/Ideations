"""피드백 수신 API — POST /api/feedback."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter

from config import FEEDBACK_PATH
from server.schemas.api_contracts import FeedbackRequest
from utils import append_jsonl, kst_now

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """피드백을 기록한다."""
    record = {
        "hypothesis_id": req.hypothesis_id,
        "action": req.action,
        "comment": req.comment,
        "submitted_at": kst_now().isoformat(),
    }
    append_jsonl(FEEDBACK_PATH, record)
    return {"status": "ok"}
