"""Stage 8 테스트 — JSONL 추가, Discord embed 페이로드 형식, 아카이브."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_PUBLISHER_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "publisher" / "scripts"
if str(_PUBLISHER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PUBLISHER_SCRIPTS))

from dashboard_writer import DashboardWriter
from discord_notifier import DiscordNotifier
from archive_manager import ArchiveManager
from utils import read_jsonl


class TestDashboardWriter:
    def test_write_batch(self, tmp_path):
        path = tmp_path / "batches.jsonl"
        writer = DashboardWriter(path=path)
        ideas = [{"service_name": "테스트 서비스", "grade": "S", "weighted_score": 4.5}]
        assert writer.write_batch("test-batch", ideas) is True

        records = read_jsonl(path)
        assert len(records) == 1
        assert records[0]["batch_id"] == "test-batch"
        assert len(records[0]["ideas"]) == 1

    def test_multiple_batches(self, tmp_path):
        path = tmp_path / "batches.jsonl"
        writer = DashboardWriter(path=path)
        writer.write_batch("b1", [{"service_name": "A"}])
        writer.write_batch("b2", [{"service_name": "B"}, {"service_name": "C"}])

        records = read_jsonl(path)
        assert len(records) == 2
        assert records[1]["batch_id"] == "b2"


class TestDiscordNotifier:
    def test_disabled_when_no_config(self, tmp_path):
        notifier = DiscordNotifier(config_path=tmp_path / "nonexistent.json")
        assert notifier.enabled is False
        assert notifier.notify_idea({"grade": "S"}) is False

    def test_disabled_when_empty_url(self, tmp_path):
        cfg = tmp_path / "webhook.json"
        cfg.write_text('{"discord_webhook_url": "", "secret": ""}')
        notifier = DiscordNotifier(config_path=cfg)
        assert notifier.enabled is False

    def test_enabled_with_valid_url(self, tmp_path):
        cfg = tmp_path / "webhook.json"
        cfg.write_text('{"discord_webhook_url": "https://discord.com/api/webhooks/test", "secret": "s"}')
        notifier = DiscordNotifier(config_path=cfg)
        assert notifier.enabled is True

    def test_embed_format(self, tmp_path):
        """Discord embed 페이로드 형식 검증."""
        cfg = tmp_path / "webhook.json"
        cfg.write_text('{"discord_webhook_url": "https://discord.com/api/webhooks/test", "secret": "s"}')
        notifier = DiscordNotifier(config_path=cfg)

        captured_payload = {}

        def mock_post(url, json=None, timeout=None):
            captured_payload.update(json)
            resp = MagicMock()
            resp.status_code = 204
            return resp

        import httpx as real_httpx
        mock_httpx = MagicMock(wraps=real_httpx)
        mock_httpx.post = mock_post

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = notifier.notify_idea({
                "grade": "S",
                "service_name": "테스트",
                "weighted_score": 4.5,
                "problem": "문제",
                "solution": "솔루션",
            })

        assert result is True
        assert "embeds" in captured_payload
        embed = captured_payload["embeds"][0]
        assert "S급" in embed["title"]
        assert embed["color"] == 0xFFD700


class TestArchiveManager:
    def test_archive_and_retrieve(self, tmp_path):
        path = tmp_path / "archive.jsonl"
        mgr = ArchiveManager(path=path)
        ideas = [
            {"service_name": "서비스A", "grade": "S"},
            {"service_name": "서비스B", "grade": "A"},
        ]
        count = mgr.archive_ideas("batch-001", ideas)
        assert count == 2

        recent = mgr.get_recent(hours=1)
        assert len(recent) == 2

    def test_get_service_names(self, tmp_path):
        path = tmp_path / "archive.jsonl"
        mgr = ArchiveManager(path=path)
        mgr.archive_ideas("b1", [{"service_name": "교통 알리미"}, {"service_name": "날씨 앱"}])

        names = mgr.get_service_names(hours=1)
        assert "교통 알리미" in names
        assert "날씨 앱" in names
