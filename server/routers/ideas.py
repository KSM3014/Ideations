"""아이디어 CRUD API — GET /api/batches, GET /api/ideas/{id}."""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Query

from config import DASHBOARD_BATCHES_PATH
from utils import read_jsonl

router = APIRouter(tags=["ideas"])


@router.get("/batches")
def list_batches(
    date: str | None = Query(None, description="YYYY-MM-DD 필터"),
    grade: str | None = Query(None, description="등급 필터 (S, A, B, C, D)"),
):
    """배치 목록을 반환한다."""
    batches = read_jsonl(DASHBOARD_BATCHES_PATH)

    if date:
        batches = [b for b in batches if b.get("timestamp", "").startswith(date)]

    results = []
    for batch in batches:
        ideas = batch.get("ideas", [])
        if grade:
            ideas = [i for i in ideas if i.get("grade") == grade]

        grade_dist = {}
        for idea in ideas:
            g = idea.get("grade", "?")
            grade_dist[g] = grade_dist.get(g, 0) + 1

        results.append({
            "batch_id": batch.get("batch_id"),
            "timestamp": batch.get("timestamp"),
            "total_ideas": len(ideas),
            "grade_distribution": grade_dist,
            "ideas": ideas,
        })

    return results


@router.get("/ideas/{idea_id}")
def get_idea(idea_id: str):
    """아이디어 상세를 반환한다."""
    batches = read_jsonl(DASHBOARD_BATCHES_PATH)

    for batch in batches:
        for idea in batch.get("ideas", []):
            if idea.get("id") == idea_id or idea.get("hypothesis_id") == idea_id:
                return {
                    "batch_id": batch.get("batch_id"),
                    **idea,
                }

    raise HTTPException(status_code=404, detail=f"Idea {idea_id} not found")
