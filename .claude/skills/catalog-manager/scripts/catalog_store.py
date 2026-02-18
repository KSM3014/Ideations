"""SQLite 카탈로그 저장소 — API CRUD, 도메인 요약, 카테고리 분포.

테이블: apis, api_parameters, api_operations, domain_summary, catalog_metadata.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import CATALOG_DB_PATH, SCHEMA_VERSION
from logger import get_logger

logger = get_logger("catalog_store")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS catalog_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS apis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id          TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    provider        TEXT DEFAULT '',
    endpoint_url    TEXT DEFAULT '',
    data_format     TEXT DEFAULT 'JSON',
    is_active       INTEGER DEFAULT 1,
    last_scanned_at TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_parameters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id      TEXT NOT NULL REFERENCES apis(api_id) ON DELETE CASCADE,
    param_name  TEXT NOT NULL,
    param_type  TEXT DEFAULT 'string',
    description TEXT DEFAULT '',
    required    INTEGER DEFAULT 0,
    UNIQUE(api_id, param_name)
);

CREATE TABLE IF NOT EXISTS api_operations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    api_id          TEXT NOT NULL REFERENCES apis(api_id) ON DELETE CASCADE,
    operation_name  TEXT NOT NULL,
    http_method     TEXT DEFAULT 'GET',
    path            TEXT DEFAULT '',
    description     TEXT DEFAULT '',
    UNIQUE(api_id, operation_name)
);

CREATE TABLE IF NOT EXISTS domain_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT UNIQUE NOT NULL,
    api_count       INTEGER DEFAULT 0,
    representative_keywords TEXT DEFAULT '',
    summary_text    TEXT DEFAULT '',
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apis_category ON apis(category);
CREATE INDEX IF NOT EXISTS idx_apis_active ON apis(is_active);
CREATE INDEX IF NOT EXISTS idx_api_params_api_id ON api_parameters(api_id);
CREATE INDEX IF NOT EXISTS idx_api_ops_api_id ON api_operations(api_id);
"""


class CatalogStore:
    """SQLite 카탈로그 DB 래퍼."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else CATALOG_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA_SQL)
            # 스키마 버전 초기화
            existing = conn.execute(
                "SELECT value FROM catalog_metadata WHERE key='schema_version'"
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO catalog_metadata (key, value) VALUES ('schema_version', ?)",
                    (SCHEMA_VERSION,),
                )
        logger.info(f"Catalog DB initialized at {self.db_path}")

    # ──── 메타데이터 ────

    def get_metadata(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM catalog_metadata WHERE key=?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_metadata(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO catalog_metadata (key, value) VALUES (?, ?)",
                (key, value),
            )

    # ──── API CRUD ────

    def upsert_api(self, api_data: dict[str, Any]) -> None:
        """API를 삽입하거나 갱신한다."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO apis (api_id, name, description, category, provider,
                   endpoint_url, data_format, is_active, last_scanned_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(api_id) DO UPDATE SET
                     name=excluded.name, description=excluded.description,
                     category=excluded.category, provider=excluded.provider,
                     endpoint_url=excluded.endpoint_url, data_format=excluded.data_format,
                     is_active=excluded.is_active, last_scanned_at=excluded.last_scanned_at,
                     updated_at=excluded.updated_at""",
                (
                    api_data["api_id"],
                    api_data.get("name", ""),
                    api_data.get("description", ""),
                    api_data.get("category", ""),
                    api_data.get("provider", ""),
                    api_data.get("endpoint_url", ""),
                    api_data.get("data_format", "JSON"),
                    api_data.get("is_active", 1),
                    api_data.get("last_scanned_at", now),
                    now,
                    now,
                ),
            )

    def get_api(self, api_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM apis WHERE api_id=?", (api_id,)).fetchone()
            return dict(row) if row else None

    def list_apis(self, *, active_only: bool = True, category: str | None = None) -> list[dict]:
        with self._conn() as conn:
            query = "SELECT * FROM apis WHERE 1=1"
            params: list[Any] = []
            if active_only:
                query += " AND is_active=1"
            if category:
                query += " AND category=?"
                params.append(category)
            query += " ORDER BY name"
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def deactivate_api(self, api_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE apis SET is_active=0, updated_at=? WHERE api_id=?",
                (datetime.utcnow().isoformat(), api_id),
            )

    def count_apis(self, *, active_only: bool = True) -> int:
        with self._conn() as conn:
            q = "SELECT COUNT(*) FROM apis"
            if active_only:
                q += " WHERE is_active=1"
            return conn.execute(q).fetchone()[0]

    # ──── 파라미터 ────

    def upsert_parameters(self, api_id: str, params: list[dict]) -> None:
        with self._conn() as conn:
            for p in params:
                conn.execute(
                    """INSERT INTO api_parameters (api_id, param_name, param_type, description, required)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(api_id, param_name) DO UPDATE SET
                         param_type=excluded.param_type,
                         description=excluded.description,
                         required=excluded.required""",
                    (
                        api_id,
                        p["param_name"],
                        p.get("param_type", "string"),
                        p.get("description", ""),
                        p.get("required", 0),
                    ),
                )

    def get_parameters(self, api_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM api_parameters WHERE api_id=?", (api_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ──── 오퍼레이션 ────

    def upsert_operations(self, api_id: str, ops: list[dict]) -> None:
        with self._conn() as conn:
            for op in ops:
                conn.execute(
                    """INSERT INTO api_operations (api_id, operation_name, http_method, path, description)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(api_id, operation_name) DO UPDATE SET
                         http_method=excluded.http_method,
                         path=excluded.path,
                         description=excluded.description""",
                    (
                        api_id,
                        op["operation_name"],
                        op.get("http_method", "GET"),
                        op.get("path", ""),
                        op.get("description", ""),
                    ),
                )

    # ──── 도메인 요약 ────

    def upsert_domain_summary(
        self, category: str, api_count: int, keywords: str, summary: str
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO domain_summary (category, api_count, representative_keywords, summary_text, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(category) DO UPDATE SET
                     api_count=excluded.api_count,
                     representative_keywords=excluded.representative_keywords,
                     summary_text=excluded.summary_text,
                     updated_at=excluded.updated_at""",
                (category, api_count, keywords, summary, now),
            )

    def get_domain_summaries(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM domain_summary ORDER BY api_count DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_category_distribution(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM apis WHERE is_active=1 GROUP BY category ORDER BY cnt DESC"
            ).fetchall()
            return {r["category"]: r["cnt"] for r in rows}
