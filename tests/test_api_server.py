"""Stage 10 테스트 — FastAPI TestClient로 엔드포인트 검증."""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not installed", allow_module_level=True)

from server.app import app
from utils import write_jsonl


@pytest.fixture
def client(tmp_path, monkeypatch):
    """테스트용 데이터 경로로 패치된 TestClient."""
    test_batches = tmp_path / "dashboard_batches.jsonl"
    test_feedback = tmp_path / "feedback.jsonl"

    monkeypatch.setattr("server.routers.ideas.DASHBOARD_BATCHES_PATH", test_batches)
    monkeypatch.setattr("server.routers.health.DASHBOARD_BATCHES_PATH", test_batches)
    monkeypatch.setattr("server.routers.feedback.FEEDBACK_PATH", test_feedback)

    write_jsonl(test_batches, [
        {
            "schema_version": "1.0",
            "batch_id": "20260218-1400-abc12345",
            "timestamp": "2026-02-18T14:00:00+09:00",
            "ideas": [
                {
                    "id": "H-001",
                    "hypothesis_id": "H-001",
                    "service_name": "스마트 교통 알리미",
                    "grade": "S",
                    "weighted_score": 4.5,
                    "problem": "실시간 교통 정보 부족",
                    "solution": "공공 교통 API 대시보드",
                    "target_buyer": "지자체",
                    "revenue_model": "SaaS",
                    "feasibility_pct": 78,
                    "matched_apis": [],
                },
                {
                    "id": "H-002",
                    "hypothesis_id": "H-002",
                    "service_name": "날씨 기반 농업 서비스",
                    "grade": "B",
                    "weighted_score": 2.8,
                    "problem": "기상 예보 활용 어려움",
                    "solution": "기상 API 농업 알림",
                    "target_buyer": "농가",
                    "revenue_model": "구독",
                    "feasibility_pct": 55,
                    "matched_apis": [],
                },
            ],
        },
    ])

    return TestClient(app)


class TestBatchesEndpoint:
    def test_list_all_batches(self, client):
        resp = client.get("/api/batches")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["batch_id"] == "20260218-1400-abc12345"
        assert data[0]["total_ideas"] == 2

    def test_filter_by_grade(self, client):
        resp = client.get("/api/batches?grade=S")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["total_ideas"] == 1

    def test_filter_by_nonexistent_date(self, client):
        resp = client.get("/api/batches?date=2099-01-01")
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestIdeasEndpoint:
    def test_get_idea_by_id(self, client):
        resp = client.get("/api/ideas/H-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service_name"] == "스마트 교통 알리미"
        assert data["grade"] == "S"

    def test_get_nonexistent_idea(self, client):
        resp = client.get("/api/ideas/MISSING")
        assert resp.status_code == 404


class TestFeedbackEndpoint:
    def test_submit_feedback(self, client):
        resp = client.post("/api/feedback", json={
            "hypothesis_id": "H-001",
            "action": "like",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_invalid_action(self, client):
        resp = client.post("/api/feedback", json={
            "hypothesis_id": "H-001",
            "action": "invalid_action",
        })
        assert resp.status_code == 422


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["last_batch_id"] == "20260218-1400-abc12345"
