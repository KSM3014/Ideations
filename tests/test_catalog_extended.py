"""2차 확장 테스트 — 카탈로그 CRUD 확장 (비활성화, 카테고리 분포, 오퍼레이션 upsert)."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SKILL_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "catalog-manager" / "scripts"
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

from catalog_store import CatalogStore


@pytest.fixture
def store(tmp_path):
    """임시 DB를 사용하는 CatalogStore 인스턴스."""
    db_path = tmp_path / "ext_catalog.sqlite3"
    return CatalogStore(db_path=db_path)


def _make_api(api_id: str, name: str = "", category: str = "", **overrides) -> dict:
    """테스트용 API 데이터 생성 헬퍼."""
    base = {
        "api_id": api_id,
        "name": name or f"API {api_id}",
        "description": "",
        "category": category,
        "provider": "테스트",
        "endpoint_url": "",
        "data_format": "JSON",
        "is_active": 1,
    }
    base.update(overrides)
    return base


class TestDeactivateMarksInactive:
    """비활성화된 API가 active_only 목록에서 제외되는지 확인."""

    def test_deactivate_marks_api_inactive(self, store):
        """API 비활성화 → active_only=True 에서 제외, active_only=False 에서 포함."""
        store.upsert_api(_make_api("API-100", name="교통량 API", category="교통"))

        # 비활성화 전: active_only=True 에 포함
        active_before = store.list_apis(active_only=True)
        assert any(a["api_id"] == "API-100" for a in active_before)

        # 비활성화
        store.deactivate_api("API-100")

        # active_only=True 에서 제외
        active_after = store.list_apis(active_only=True)
        assert not any(a["api_id"] == "API-100" for a in active_after)

        # active_only=False 에서는 포함
        all_apis = store.list_apis(active_only=False)
        assert any(a["api_id"] == "API-100" for a in all_apis)

        # 비활성화 상태 확인
        api = store.get_api("API-100")
        assert api["is_active"] == 0


class TestCategoryDistributionMultiple:
    """다수 카테고리의 분포 정확성."""

    def test_category_distribution_multiple(self, store):
        """교통 x2, 환경 x1, 농업 x3 → 분포 카운트 정확."""
        # 교통 2개
        store.upsert_api(_make_api("T-001", name="교통1", category="교통"))
        store.upsert_api(_make_api("T-002", name="교통2", category="교통"))

        # 환경 1개
        store.upsert_api(_make_api("E-001", name="환경1", category="환경"))

        # 농업 3개
        store.upsert_api(_make_api("A-001", name="농업1", category="농업"))
        store.upsert_api(_make_api("A-002", name="농업2", category="농업"))
        store.upsert_api(_make_api("A-003", name="농업3", category="농업"))

        dist = store.get_category_distribution()

        assert dist["교통"] == 2
        assert dist["환경"] == 1
        assert dist["농업"] == 3
        assert len(dist) == 3


class TestOperationsUpsert:
    """오퍼레이션 upsert 테스트."""

    def test_operations_upsert(self, store):
        """upsert_operations 후 오퍼레이션이 DB에 저장되는지 확인."""
        # API 먼저 생성
        store.upsert_api(_make_api("API-OPS", name="오퍼레이션 테스트 API", category="테스트"))

        # 오퍼레이션 추가
        ops = [
            {"operation_name": "getTraffic", "http_method": "GET", "path": "/traffic", "description": "교통량 조회"},
            {"operation_name": "getWeather", "http_method": "GET", "path": "/weather", "description": "날씨 조회"},
        ]
        store.upsert_operations("API-OPS", ops)

        # 직접 DB 쿼리로 확인
        import sqlite3
        conn = sqlite3.connect(str(store.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM api_operations WHERE api_id=?", ("API-OPS",)
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        op_names = {r["operation_name"] for r in rows}
        assert "getTraffic" in op_names
        assert "getWeather" in op_names

        # upsert 재실행 (업데이트) — 중복 없이 갱신
        ops_updated = [
            {"operation_name": "getTraffic", "http_method": "GET", "path": "/traffic/v2", "description": "교통량 조회 v2"},
        ]
        store.upsert_operations("API-OPS", ops_updated)

        conn = sqlite3.connect(str(store.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM api_operations WHERE api_id=?", ("API-OPS",)
        ).fetchall()
        conn.close()

        # 여전히 2개 (getTraffic 업데이트, getWeather 유지)
        assert len(rows) == 2
        traffic_op = [r for r in rows if r["operation_name"] == "getTraffic"][0]
        assert traffic_op["path"] == "/traffic/v2"
