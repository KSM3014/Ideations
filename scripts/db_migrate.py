"""DB 스키마 마이그레이션 — schema_version 기반 순차 적용.

catalog_metadata 테이블의 schema_version 키를 읽어 현재 버전을 확인하고,
등록된 마이그레이션을 순차 적용한다.

사용법:
    python db_migrate.py                    # 최신 버전까지 마이그레이션
    python db_migrate.py --target 1.1       # 특정 버전까지
    python db_migrate.py --current          # 현재 버전 확인만
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_CATALOG_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "catalog-manager" / "scripts"
if str(_CATALOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_CATALOG_SCRIPTS))

from config import CATALOG_DB_PATH, SCHEMA_VERSION
from logger import get_logger

logger = get_logger("db_migrate")


# ──────────────────────────── 마이그레이션 레지스트리 ────────────────────────────

# (from_version, to_version) → migration_fn
_MIGRATIONS: dict[tuple[str, str], Callable] = {}


def register_migration(from_ver: str, to_ver: str):
    """마이그레이션 함수를 등록하는 데코레이터."""

    def decorator(fn: Callable):
        _MIGRATIONS[(from_ver, to_ver)] = fn
        return fn

    return decorator


# ── 마이그레이션 정의 ──

@register_migration("1.0", "1.1")
def migrate_1_0_to_1_1(conn) -> None:
    """v1.0 → v1.1: api_operations 테이블에 deprecated 컬럼 추가."""
    logger.info("Applying migration 1.0 → 1.1")
    try:
        conn.execute("ALTER TABLE api_operations ADD COLUMN deprecated INTEGER DEFAULT 0")
        conn.commit()
    except Exception as e:
        if "duplicate column" in str(e).lower():
            logger.info("Column already exists — skipping")
        else:
            raise


# ──────────────────────────── 마이그레이션 실행기 ────────────────────────────


def _version_key(ver: str) -> tuple[int, ...]:
    """버전 문자열을 비교 가능한 튜플로 변환."""
    return tuple(int(x) for x in ver.split("."))


def get_migration_path(current: str, target: str) -> list[tuple[str, str]]:
    """현재 버전에서 목표 버전까지의 마이그레이션 경로를 반환한다."""
    path = []
    visited = set()
    cur = current

    while _version_key(cur) < _version_key(target):
        found = False
        for (from_v, to_v) in sorted(_MIGRATIONS.keys(), key=lambda x: _version_key(x[1])):
            if from_v == cur and (from_v, to_v) not in visited:
                path.append((from_v, to_v))
                visited.add((from_v, to_v))
                cur = to_v
                found = True
                break

        if not found:
            break

    return path


class DBMigrator:
    """DB 스키마 마이그레이터."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or CATALOG_DB_PATH
        self._conn = None

    def _connect(self):
        import sqlite3

        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_current_version(self) -> str:
        """현재 스키마 버전을 조회한다."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT value FROM catalog_metadata WHERE key = 'schema_version'"
            )
            row = cursor.fetchone()
            return row[0] if row else "1.0"
        except Exception:
            return "1.0"

    def set_version(self, version: str) -> None:
        """스키마 버전을 업데이트한다."""
        conn = self._connect()
        conn.execute(
            "INSERT OR REPLACE INTO catalog_metadata (key, value) VALUES ('schema_version', ?)",
            (version,),
        )
        conn.commit()

    def migrate(self, target: str | None = None) -> dict[str, Any]:
        """마이그레이션을 실행한다.

        Args:
            target: 목표 버전 (None이면 최신 config.SCHEMA_VERSION)

        Returns:
            {"from": str, "to": str, "applied": int, "steps": [...]}
        """
        target = target or SCHEMA_VERSION
        current = self.get_current_version()

        if _version_key(current) >= _version_key(target):
            logger.info(f"Already at version {current} (target: {target})")
            return {"from": current, "to": current, "applied": 0, "steps": []}

        path = get_migration_path(current, target)
        if not path:
            logger.warning(f"No migration path from {current} to {target}")
            return {"from": current, "to": current, "applied": 0, "steps": []}

        logger.info(f"Migrating {current} → {target} ({len(path)} steps)")

        conn = self._connect()
        applied_steps = []

        for from_v, to_v in path:
            migration_fn = _MIGRATIONS[(from_v, to_v)]
            try:
                migration_fn(conn)
                self.set_version(to_v)
                applied_steps.append(f"{from_v} → {to_v}")
                logger.info(f"Applied: {from_v} → {to_v}")
            except Exception as e:
                logger.error(f"Migration {from_v} → {to_v} failed: {e}")
                raise

        final_version = self.get_current_version()
        logger.info(f"Migration complete: {current} → {final_version}")

        return {
            "from": current,
            "to": final_version,
            "applied": len(applied_steps),
            "steps": applied_steps,
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="DB 스키마 마이그레이션")
    parser.add_argument("--target", type=str, help="목표 버전 (기본: config.SCHEMA_VERSION)")
    parser.add_argument("--current", action="store_true", help="현재 버전만 출력")
    args = parser.parse_args()

    migrator = DBMigrator()

    try:
        if args.current:
            ver = migrator.get_current_version()
            print(f"Current schema version: {ver}")
            return

        result = migrator.migrate(target=args.target)
        print(f"Migration result: {result}")
    finally:
        migrator.close()


if __name__ == "__main__":
    main()
