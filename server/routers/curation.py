"""큐레이션 API — 아이디어 선별/게시/내보내기.

POST /api/curation/{idea_id} — 아이디어 상태 설정 (published/hold/rejected)
DELETE /api/curation — 전체 큐레이션 상태 초기화
GET /api/curation/stats — 큐레이션 통계
GET /api/curation/export/md — 게시된 아이디어 마크다운 내보내기
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import DASHBOARD_BATCHES_PATH, DATA_DIR
from utils import kst_now, read_jsonl

router = APIRouter(tags=["curation"])

CURATION_PATH = DATA_DIR / "curation_state.json"


class CurationAction(BaseModel):
    status: str  # "published" | "hold" | "rejected"


def _load_state() -> dict[str, Any]:
    if CURATION_PATH.exists():
        try:
            with open(CURATION_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"curated": {}}


def _save_state(state: dict) -> None:
    CURATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CURATION_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(CURATION_PATH)


def _get_all_ideas() -> list[dict[str, Any]]:
    """dashboard_batches.jsonl에서 모든 아이디어를 추출한다."""
    batches = read_jsonl(DASHBOARD_BATCHES_PATH)
    ideas = []
    for batch in batches:
        for idea in batch.get("ideas", []):
            idea["_batch_id"] = batch.get("batch_id", "")
            idea["_batch_ts"] = batch.get("timestamp", "")
            ideas.append(idea)
    return ideas


@router.post("/curation/{idea_id}")
def set_curation(idea_id: str, action: CurationAction):
    """아이디어 큐레이션 상태를 설정한다."""
    if action.status not in ("published", "hold", "rejected", "none"):
        raise HTTPException(400, "status must be: published, hold, rejected, none")

    state = _load_state()
    if action.status == "none":
        state["curated"].pop(idea_id, None)
    else:
        state["curated"][idea_id] = {
            "status": action.status,
            "updated_at": kst_now().isoformat(),
        }
    _save_state(state)
    return {"status": "ok", "idea_id": idea_id, "curation": action.status}


@router.delete("/curation")
def reset_curation():
    """전체 큐레이션 상태를 초기화한다."""
    _save_state({"curated": {}})
    return {"status": "ok", "message": "All curation state reset"}


@router.get("/curation/stats")
def curation_stats():
    """큐레이션 통계를 반환한다."""
    state = _load_state()
    ideas = _get_all_ideas()
    batches = read_jsonl(DASHBOARD_BATCHES_PATH)

    grade_dist = {}
    for idea in ideas:
        g = idea.get("grade", "?")
        grade_dist[g] = grade_dist.get(g, 0) + 1

    curated = state.get("curated", {})
    published = sum(1 for v in curated.values() if v.get("status") == "published")
    hold = sum(1 for v in curated.values() if v.get("status") == "hold")
    rejected = sum(1 for v in curated.values() if v.get("status") == "rejected")

    last_ts = ""
    if batches:
        last_ts = batches[-1].get("timestamp", "")[:10]

    return {
        "total_batches": len(batches),
        "total_ideas": len(ideas),
        "grade_distribution": grade_dist,
        "published_count": published,
        "hold_count": hold,
        "rejected_count": rejected,
        "last_batch_date": last_ts,
    }


@router.get("/curation/export/md")
def export_published_md():
    """게시된 아이디어를 마크다운으로 내보낸다."""
    state = _load_state()
    curated = state.get("curated", {})
    ideas = _get_all_ideas()

    published_ids = {k for k, v in curated.items() if v.get("status") == "published"}

    published_ideas = []
    for idea in ideas:
        iid = idea.get("id") or idea.get("hypothesis_id", "")
        if iid in published_ids:
            published_ideas.append(idea)

    # 점수 내림차순
    published_ideas.sort(key=lambda x: x.get("weighted_score", x.get("numrv_score", 0)), reverse=True)

    now = kst_now().isoformat()
    lines = [
        "# Published API Ideas",
        f"- generated_at: {now}",
        f"- published_count: {len(published_ideas)}",
        "",
    ]

    for i, idea in enumerate(published_ideas, 1):
        grade = idea.get("grade", "?")
        name = idea.get("service_name", "Untitled")
        score = idea.get("weighted_score", idea.get("numrv_score", 0))
        problem = idea.get("problem", "")
        solution = idea.get("concept") or idea.get("solution", "")
        target = idea.get("target") or idea.get("target_buyer", "")
        revenue = idea.get("revenue_model", "")
        apis = idea.get("matched_apis", [])
        api_names = ", ".join(a.get("name", a.get("api_id", "?"))[:40] for a in apis[:5])

        lines.extend([
            f"## {i}. [{grade}] {name} (score: {score:.2f})",
            f"- **Problem**: {problem}",
            f"- **Solution**: {solution}",
            f"- **Target**: {target}",
            f"- **Revenue**: {revenue}",
            f"- **APIs**: {api_names or 'N/A'}",
            "",
        ])

    return {"markdown": "\n".join(lines), "count": len(published_ideas)}
