"""MVP 게이트 테스트 #1 — 원자적 JSON 쓰기, JSONL 처리, 배치ID 형식."""

import json
import re
from pathlib import Path

import pytest

from utils import (
    append_jsonl,
    atomic_json_write,
    generate_batch_id,
    kst_now,
    read_jsonl,
    write_jsonl,
)


class TestAtomicJsonWrite:
    def test_write_and_read(self, tmp_path: Path):
        target = tmp_path / "out.json"
        data = {"key": "값", "nested": [1, 2, 3]}
        atomic_json_write(target, data)

        assert target.exists()
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded == data

    def test_no_tmp_file_left_on_success(self, tmp_path: Path):
        target = tmp_path / "clean.json"
        atomic_json_write(target, {"ok": True})

        tmp_file = target.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_creates_parent_dirs(self, tmp_path: Path):
        target = tmp_path / "sub" / "deep" / "data.json"
        atomic_json_write(target, [1, 2])
        assert target.exists()

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "over.json"
        atomic_json_write(target, {"v": 1})
        atomic_json_write(target, {"v": 2})

        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert loaded["v"] == 2

    def test_failure_cleans_tmp(self, tmp_path: Path):
        target = tmp_path / "fail.json"

        class BadObj:
            pass  # not JSON serializable

        with pytest.raises(TypeError):
            atomic_json_write(target, BadObj())

        assert not target.exists()
        assert not target.with_suffix(".tmp").exists()


class TestJsonl:
    def test_read_nonexistent_returns_empty(self, tmp_path: Path):
        result = read_jsonl(tmp_path / "missing.jsonl")
        assert result == []

    def test_append_and_read(self, tmp_path: Path):
        path = tmp_path / "log.jsonl"
        append_jsonl(path, {"a": 1})
        append_jsonl(path, {"b": 2})

        records = read_jsonl(path)
        assert len(records) == 2
        assert records[0]["a"] == 1
        assert records[1]["b"] == 2

    def test_write_jsonl_atomic(self, tmp_path: Path):
        path = tmp_path / "atomic.jsonl"
        records = [{"x": i} for i in range(5)]
        write_jsonl(path, records)

        loaded = read_jsonl(path)
        assert len(loaded) == 5
        assert loaded[4]["x"] == 4

    def test_write_jsonl_overwrites(self, tmp_path: Path):
        path = tmp_path / "ow.jsonl"
        write_jsonl(path, [{"v": 1}])
        write_jsonl(path, [{"v": 2}, {"v": 3}])

        loaded = read_jsonl(path)
        assert len(loaded) == 2

    def test_empty_lines_ignored(self, tmp_path: Path):
        path = tmp_path / "sparse.jsonl"
        path.write_text('{"a":1}\n\n{"b":2}\n  \n', encoding="utf-8")

        records = read_jsonl(path)
        assert len(records) == 2


class TestBatchId:
    def test_format(self):
        bid = generate_batch_id()
        # YYYYMMDD-HHMM-xxxxxxxx
        assert re.match(r"^\d{8}-\d{4}-[0-9a-f]{8}$", bid)

    def test_uniqueness(self):
        ids = {generate_batch_id() for _ in range(100)}
        assert len(ids) == 100


class TestKstNow:
    def test_timezone_offset(self):
        now = kst_now()
        assert now.utcoffset().total_seconds() == 9 * 3600
