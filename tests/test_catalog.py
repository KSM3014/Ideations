"""Stage 1 테스트 — DB CRUD, 도메인 요약, 메타데이터."""

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
    db_path = tmp_path / "test_catalog.sqlite3"
    return CatalogStore(db_path=db_path)


class TestCatalogMetadata:
    def test_schema_version_initialized(self, store):
        version = store.get_metadata("schema_version")
        assert version == "1.0"

    def test_set_and_get_metadata(self, store):
        store.set_metadata("last_scan", "2026-02-18T10:00:00")
        assert store.get_metadata("last_scan") == "2026-02-18T10:00:00"

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_metadata("missing_key") is None


class TestApiCRUD:
    def _sample_api(self, api_id: str = "API-001", **overrides) -> dict:
        base = {
            "api_id": api_id,
            "name": "교통량 정보 서비스",
            "description": "실시간 교통량 데이터 제공",
            "category": "교통",
            "provider": "국토교통부",
            "endpoint_url": "https://api.data.go.kr/traffic",
            "data_format": "JSON",
            "is_active": 1,
        }
        base.update(overrides)
        return base

    def test_upsert_and_get(self, store):
        store.upsert_api(self._sample_api())
        api = store.get_api("API-001")
        assert api is not None
        assert api["name"] == "교통량 정보 서비스"
        assert api["category"] == "교통"

    def test_upsert_update(self, store):
        store.upsert_api(self._sample_api())
        store.upsert_api(self._sample_api(name="교통량 정보 v2"))
        api = store.get_api("API-001")
        assert api["name"] == "교통량 정보 v2"

    def test_list_apis_active_only(self, store):
        store.upsert_api(self._sample_api("API-001"))
        store.upsert_api(self._sample_api("API-002", name="날씨 API", is_active=0))
        active = store.list_apis(active_only=True)
        assert len(active) == 1
        assert active[0]["api_id"] == "API-001"

    def test_list_apis_by_category(self, store):
        store.upsert_api(self._sample_api("API-001", category="교통"))
        store.upsert_api(self._sample_api("API-002", name="날씨", category="기상"))
        traffic = store.list_apis(category="교통")
        assert len(traffic) == 1

    def test_deactivate_api(self, store):
        store.upsert_api(self._sample_api())
        store.deactivate_api("API-001")
        api = store.get_api("API-001")
        assert api["is_active"] == 0

    def test_count_apis(self, store):
        for i in range(5):
            store.upsert_api(self._sample_api(f"API-{i:03d}"))
        assert store.count_apis() == 5

    def test_get_nonexistent(self, store):
        assert store.get_api("MISSING") is None


class TestParameters:
    def test_upsert_and_get(self, store):
        store.upsert_api({"api_id": "API-001", "name": "Test"})
        store.upsert_parameters("API-001", [
            {"param_name": "시군구코드", "param_type": "string", "description": "시군구 코드", "required": 1},
            {"param_name": "날짜", "param_type": "string", "description": "조회 날짜"},
        ])
        params = store.get_parameters("API-001")
        assert len(params) == 2
        assert any(p["param_name"] == "시군구코드" for p in params)


class TestDomainSummary:
    def test_upsert_and_list(self, store):
        store.upsert_domain_summary("교통", 45, "교통량, 도로, 버스", "교통 관련 45개 API")
        store.upsert_domain_summary("기상", 20, "날씨, 기온, 강수", "기상 관련 20개 API")
        summaries = store.get_domain_summaries()
        assert len(summaries) == 2
        assert summaries[0]["category"] == "교통"  # api_count DESC

    def test_update_summary(self, store):
        store.upsert_domain_summary("교통", 45, "교통량", "v1")
        store.upsert_domain_summary("교통", 50, "교통량, 도로", "v2")
        summaries = store.get_domain_summaries()
        assert len(summaries) == 1
        assert summaries[0]["api_count"] == 50


class TestCategoryDistribution:
    def test_distribution(self, store):
        for i in range(3):
            store.upsert_api({"api_id": f"T-{i}", "name": f"교통{i}", "category": "교통"})
        for i in range(2):
            store.upsert_api({"api_id": f"W-{i}", "name": f"기상{i}", "category": "기상"})

        dist = store.get_category_distribution()
        assert dist["교통"] == 3
        assert dist["기상"] == 2
