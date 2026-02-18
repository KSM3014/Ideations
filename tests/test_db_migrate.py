"""2차 확장 테스트 — DB 마이그레이션 (db_migrate.py)."""

import sqlite3
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SCRIPTS = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_CATALOG_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "catalog-manager" / "scripts"
if str(_CATALOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_CATALOG_SCRIPTS))

from catalog_store import CatalogStore
from db_migrate import DBMigrator


class TestDBMigration:
    """DB 마이그레이션 확장 테스트."""

    def test_migration_1_0_to_1_1(self, tmp_path):
        """v1.0 → v1.1 마이그레이션: api_operations 에 deprecated 컬럼 추가."""
        db_path = tmp_path / "migrate_test.sqlite3"

        # CatalogStore 초기화 → schema_version = "1.0"
        store = CatalogStore(db_path=db_path)
        assert store.get_metadata("schema_version") == "1.0"

        # DBMigrator 로 1.1 까지 마이그레이션
        migrator = DBMigrator(db_path=db_path)
        try:
            result = migrator.migrate(target="1.1")

            # 마이그레이션 결과 검증
            assert result["from"] == "1.0"
            assert result["to"] == "1.1"
            assert result["applied"] == 1
            assert "1.0 → 1.1" in result["steps"]

            # 버전 업데이트 확인
            assert migrator.get_current_version() == "1.1"

            # deprecated 컬럼 존재 확인
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("PRAGMA table_info(api_operations)")
            columns = [row[1] for row in cursor.fetchall()]
            conn.close()

            assert "deprecated" in columns
        finally:
            migrator.close()

    def test_already_at_target_skips(self, tmp_path):
        """현재 버전이 이미 목표 버전 이상이면 마이그레이션을 건너뛴다."""
        db_path = tmp_path / "skip_test.sqlite3"

        # CatalogStore 초기화 → schema_version = "1.0"
        store = CatalogStore(db_path=db_path)
        assert store.get_metadata("schema_version") == "1.0"

        # target="1.0" 으로 마이그레이션 → 이미 도달
        migrator = DBMigrator(db_path=db_path)
        try:
            result = migrator.migrate(target="1.0")

            assert result["applied"] == 0
            assert result["steps"] == []
            assert result["from"] == "1.0"
            assert result["to"] == "1.0"
        finally:
            migrator.close()
