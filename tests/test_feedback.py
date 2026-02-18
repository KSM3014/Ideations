"""2차 확장 테스트 — 피드백 JSONL 기록/읽기."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils import append_jsonl, read_jsonl


class TestFeedbackRecording:
    def test_blacklist_action_recorded(self, tmp_path):
        """blacklist 피드백을 JSONL에 기록하고 읽어올 수 있어야 한다."""
        path = tmp_path / "feedback.jsonl"
        record = {
            "hypothesis_id": "H-001",
            "action": "blacklist",
            "timestamp": "2026-02-18T10:00:00+09:00",
        }
        append_jsonl(path, record)

        records = read_jsonl(path)
        assert len(records) == 1
        assert records[0]["action"] == "blacklist"
        assert records[0]["hypothesis_id"] == "H-001"

    def test_like_action_recorded(self, tmp_path):
        """like 피드백을 JSONL에 기록하고 읽어올 수 있어야 한다."""
        path = tmp_path / "feedback.jsonl"
        record = {
            "hypothesis_id": "H-002",
            "action": "like",
            "timestamp": "2026-02-18T10:01:00+09:00",
        }
        append_jsonl(path, record)

        records = read_jsonl(path)
        assert len(records) == 1
        assert records[0]["action"] == "like"
        assert records[0]["hypothesis_id"] == "H-002"

    def test_dislike_action_recorded(self, tmp_path):
        """dislike 피드백을 JSONL에 기록하고 읽어올 수 있어야 한다."""
        path = tmp_path / "feedback.jsonl"
        record = {
            "hypothesis_id": "H-003",
            "action": "dislike",
            "timestamp": "2026-02-18T10:02:00+09:00",
        }
        append_jsonl(path, record)

        records = read_jsonl(path)
        assert len(records) == 1
        assert records[0]["action"] == "dislike"
        assert records[0]["hypothesis_id"] == "H-003"

    def test_comment_action_recorded(self, tmp_path):
        """comment 피드백(note 필드 포함)을 JSONL에 기록하고 읽어올 수 있어야 한다."""
        path = tmp_path / "feedback.jsonl"
        record = {
            "hypothesis_id": "H-004",
            "action": "comment",
            "note": "이 아이디어는 교통 분야에서 유망합니다.",
            "timestamp": "2026-02-18T10:03:00+09:00",
        }
        append_jsonl(path, record)

        records = read_jsonl(path)
        assert len(records) == 1
        assert records[0]["action"] == "comment"
        assert records[0]["note"] == "이 아이디어는 교통 분야에서 유망합니다."

    def test_multiple_feedback_for_same_idea(self, tmp_path):
        """동일 hypothesis_id에 대한 여러 피드백이 모두 기록되어야 한다."""
        path = tmp_path / "feedback.jsonl"
        target_id = "H-005"

        feedbacks = [
            {"hypothesis_id": target_id, "action": "like", "timestamp": "2026-02-18T10:00:00+09:00"},
            {"hypothesis_id": target_id, "action": "comment", "note": "좋은 아이디어!", "timestamp": "2026-02-18T10:05:00+09:00"},
            {"hypothesis_id": target_id, "action": "blacklist", "timestamp": "2026-02-18T10:10:00+09:00"},
        ]

        for fb in feedbacks:
            append_jsonl(path, fb)

        records = read_jsonl(path)
        assert len(records) == 3

        target_records = [r for r in records if r["hypothesis_id"] == target_id]
        assert len(target_records) == 3
        actions = [r["action"] for r in target_records]
        assert "like" in actions
        assert "comment" in actions
        assert "blacklist" in actions
