"""공통 유틸리티 — 원자적 JSON 쓰기, JSONL 읽기/쓰기, 배치ID 생성, KST 시간."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))


def kst_now() -> datetime:
    """현재 KST 시각을 반환한다."""
    return datetime.now(KST)


def generate_batch_id() -> str:
    """배치 ID를 생성한다. 형식: YYYYMMDD-HHMM-{short_uuid}"""
    now = kst_now()
    short = uuid.uuid4().hex[:8]
    return f"{now.strftime('%Y%m%d-%H%M')}-{short}"


# ──────────────────────────── 원자적 JSON 쓰기 ────────────────────────────


def atomic_json_write(path: Path | str, data: Any) -> None:
    """원자적으로 JSON 파일을 작성한다 (.tmp → os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


# ──────────────────────────── JSONL 읽기/쓰기 ────────────────────────────


def read_jsonl(path: Path | str) -> list[dict]:
    """JSONL 파일을 읽어 딕셔너리 리스트로 반환한다. 파일이 없으면 빈 리스트."""
    path = Path(path)
    if not path.exists():
        return []
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append_jsonl(path: Path | str, record: dict) -> None:
    """JSONL 파일에 한 줄을 추가한다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_jsonl(path: Path | str, records: list[dict]) -> None:
    """JSONL 파일을 원자적으로 덮어쓴다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
