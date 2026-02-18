"""2차 확장 테스트 — Discord 알림: embed 색상, 재시도, httpx 미설치, 설정 누락."""

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_PUBLISHER_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "publisher" / "scripts"
if str(_PUBLISHER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PUBLISHER_SCRIPTS))

from discord_notifier import DiscordNotifier


def _make_notifier_with_webhook(tmp_path, webhook_url="https://discord.com/api/webhooks/test"):
    """유효한 웹훅 설정이 있는 DiscordNotifier를 생성한다."""
    config_path = tmp_path / "webhook_config.json"
    config_path.write_text(
        json.dumps({"discord_webhook_url": webhook_url}),
        encoding="utf-8",
    )
    return DiscordNotifier(config_path=config_path)


class TestSGradeGoldEmbed:
    def test_s_grade_sends_gold_embed(self, tmp_path):
        """S등급 아이디어는 금색(0xFFD700) embed를 전송해야 한다."""
        notifier = _make_notifier_with_webhook(tmp_path)
        sent_payloads = []

        mock_httpx = ModuleType("httpx")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_post = MagicMock(return_value=mock_resp)
        mock_httpx.post = mock_post

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            notifier.notify_idea({
                "grade": "S",
                "service_name": "테스트 서비스",
                "weighted_score": 4.8,
                "problem": "문제 설명",
                "solution": "솔루션 설명",
            })

        assert mock_post.called
        payload = mock_post.call_args[1]["json"]
        embed = payload["embeds"][0]
        assert embed["color"] == 0xFFD700


class TestAGradeBlueEmbed:
    def test_a_grade_sends_blue_embed(self, tmp_path):
        """A등급 아이디어는 파란색(0x4169E1) embed를 전송해야 한다."""
        notifier = _make_notifier_with_webhook(tmp_path)

        mock_httpx = ModuleType("httpx")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_post = MagicMock(return_value=mock_resp)
        mock_httpx.post = mock_post

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            notifier.notify_idea({
                "grade": "A",
                "service_name": "A급 서비스",
                "weighted_score": 3.8,
                "problem": "문제",
                "solution": "솔루션",
            })

        assert mock_post.called
        payload = mock_post.call_args[1]["json"]
        embed = payload["embeds"][0]
        assert embed["color"] == 0x4169E1


class TestSystemAlertRedEmbed:
    def test_system_alert_sends_red_embed(self, tmp_path):
        """시스템 경고는 빨간색(0xFF4500) embed를 전송해야 한다."""
        notifier = _make_notifier_with_webhook(tmp_path)

        mock_httpx = ModuleType("httpx")
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_post = MagicMock(return_value=mock_resp)
        mock_httpx.post = mock_post

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            notifier.notify_system_alert("CPU 사용률 90% 초과")

        assert mock_post.called
        payload = mock_post.call_args[1]["json"]
        embed = payload["embeds"][0]
        assert embed["color"] == 0xFF4500


class TestFailedSendRetries:
    def test_failed_send_retries_3_times(self, tmp_path):
        """전송 실패 시 총 4회(1 초기 + 3 재시도) 호출해야 한다."""
        notifier = _make_notifier_with_webhook(tmp_path)

        mock_httpx = ModuleType("httpx")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post = MagicMock(return_value=mock_resp)
        mock_httpx.post = mock_post

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            with patch("discord_notifier.time.sleep"):
                result = notifier._send({"embeds": [{"title": "test"}]})

        assert result is False
        assert mock_post.call_count == 4  # 1 initial + 3 retries


class TestHttpxNotInstalled:
    def test_httpx_not_installed_returns_false(self, tmp_path):
        """httpx가 설치되지 않았으면 _send가 False를 반환해야 한다."""
        notifier = _make_notifier_with_webhook(tmp_path)

        # httpx import를 실패하게 만든다
        with patch.dict("sys.modules", {"httpx": None}):
            result = notifier._send({"embeds": [{"title": "test"}]})

        assert result is False


class TestWebhookUrlMissing:
    def test_webhook_url_missing_disables(self, tmp_path):
        """설정 파일이 없으면 enabled=False여야 한다."""
        missing_config = tmp_path / "nonexistent_config.json"
        notifier = DiscordNotifier(config_path=missing_config)
        assert notifier.enabled is False
