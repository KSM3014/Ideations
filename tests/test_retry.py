"""2차 확장 테스트 — 재시도/지수 백오프 동작 검증."""

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

from scripts.run_engine import ClaudeCLIInvoker
from discord_notifier import DiscordNotifier


class TestExponentialBackoffTiming:
    def test_exponential_backoff_timing(self):
        """재시도 대기 시간이 지수적으로 증가해야 한다 (2초, 4초)."""
        invoker = ClaudeCLIInvoker(max_retries=2, wait_base=2, wait_max=30)

        with patch.object(invoker, "_run_subprocess", return_value="not json"):
            with patch("scripts.run_engine.time.sleep") as mock_sleep:
                with pytest.raises(RuntimeError):
                    invoker.invoke("test", phase=2)

        # 2회 재시도이므로 sleep은 2번 호출
        assert mock_sleep.call_count == 2
        # 첫 번째 대기: wait_base * 2^0 = 2초
        assert mock_sleep.call_args_list[0][0][0] == 2
        # 두 번째 대기: wait_base * 2^1 = 4초
        assert mock_sleep.call_args_list[1][0][0] == 4


class TestMaxRetryThenStop:
    def test_max_retry_then_stop(self):
        """max_retries + 1 시도 후 RuntimeError를 발생시켜야 한다."""
        max_retries = 3
        invoker = ClaudeCLIInvoker(max_retries=max_retries, wait_base=0, wait_max=0)

        mock_fn = MagicMock(return_value="not json")
        with patch.object(invoker, "_run_subprocess", mock_fn):
            with pytest.raises(RuntimeError, match=f"failed after {max_retries + 1} attempts"):
                invoker.invoke("test", phase=2)

        # 총 호출 횟수: 1(초기) + max_retries(재시도)
        assert mock_fn.call_count == max_retries + 1


class TestDiscordWebhookRetry:
    def test_discord_webhook_retry_3_times(self, tmp_path):
        """Discord 웹훅이 실패 시 3회 재시도(총 4회)해야 한다."""
        config_path = tmp_path / "webhook_config.json"
        config_path.write_text(
            json.dumps({"discord_webhook_url": "https://discord.com/api/webhooks/test"}),
            encoding="utf-8",
        )
        notifier = DiscordNotifier(config_path=config_path)

        mock_httpx = ModuleType("httpx")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post = MagicMock(return_value=mock_resp)
        mock_httpx.post = mock_post

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            with patch("discord_notifier.time.sleep") as mock_sleep:
                result = notifier._send({"embeds": [{"title": "retry test"}]})

        assert result is False
        assert mock_post.call_count == 4  # 1 initial + 3 retries
        # sleep은 3회 호출 (각 재시도 전)
        assert mock_sleep.call_count == 3
