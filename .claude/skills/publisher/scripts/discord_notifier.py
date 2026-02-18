"""Discord 웹훅 알림 — Rich embed (S/A급 알림 + 시스템 경고)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import RETRY_DISCORD_WEBHOOK, WEBHOOK_CONFIG_PATH
from logger import get_logger

logger = get_logger("discord_notifier")


class DiscordNotifier:
    """Discord 웹훅으로 리치 embed를 전송한다."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        self.config_path = Path(config_path) if config_path else WEBHOOK_CONFIG_PATH
        self._webhook_url: str | None = None
        self._load_config()

    def _load_config(self) -> None:
        if not self.config_path.exists():
            logger.warning(f"Webhook config not found: {self.config_path} — Discord disabled")
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self._webhook_url = cfg.get("discord_webhook_url", "").strip() or None
            if not self._webhook_url:
                logger.warning("Discord webhook URL is empty — notifications disabled")
        except Exception as e:
            logger.error(f"Failed to load webhook config: {e}")

    @property
    def enabled(self) -> bool:
        return self._webhook_url is not None

    def notify_idea(self, idea: dict[str, Any]) -> bool:
        """S/A급 아이디어를 Discord에 전송한다."""
        if not self.enabled:
            return False

        grade = idea.get("grade", "?")
        emoji = "💎" if grade == "S" else "⭐"
        service_name = idea.get("service_name", "알 수 없음")
        score = idea.get("weighted_score", 0)
        problem = idea.get("problem", "")
        solution = idea.get("solution", "")
        target = idea.get("target_buyer", "")
        revenue = idea.get("revenue_model", "")
        scores = idea.get("scores", {})
        matched_apis = idea.get("matched_apis", [])
        competitors = idea.get("competitors_count", 0)
        feasibility = idea.get("feasibility_pct", 0)
        validation = idea.get("validation_score", 0)

        # NUMR-V 점수 상세
        score_detail = " / ".join(
            f"{k}={v}" for k, v in scores.items()
        ) if scores else "N/A"

        # 매칭된 API 이름 (최대 3개)
        api_names = ", ".join(
            a.get("name", a.get("api_id", "?"))[:30] for a in matched_apis[:3]
        ) if matched_apis else "N/A"
        if len(matched_apis) > 3:
            api_names += f" 외 {len(matched_apis) - 3}개"

        embed = {
            "title": f"{emoji} {grade}급 아이디어 발견!",
            "description": f"**{service_name}**\nNUMR-V 종합: **{score:.2f}** ({grade}급)",
            "color": 0xFFD700 if grade == "S" else 0x4169E1,
            "fields": [
                {"name": "🎯 해결할 문제", "value": problem[:300] or "N/A", "inline": False},
                {"name": "💡 솔루션 개요", "value": solution[:300] or "N/A", "inline": False},
                {"name": "👥 타겟 고객", "value": target[:150] or "N/A", "inline": True},
                {"name": "💰 수익 모델", "value": revenue[:150] or "N/A", "inline": True},
                {"name": "📊 NUMR-V 상세", "value": score_detail, "inline": False},
                {"name": "🔗 활용 API", "value": api_names, "inline": True},
                {"name": "🏁 경쟁사", "value": f"{competitors}개 확인" if competitors else "N/A", "inline": True},
                {"name": "✅ 검증 결과", "value": f"적합도 {feasibility}% / 검증 {validation}점", "inline": True},
            ],
            "footer": {"text": "API Ideation Engine v6.0"},
        }
        return self._send({"embeds": [embed]})

    def notify_system_alert(self, message: str) -> bool:
        """시스템 경고를 Discord에 전송한다."""
        if not self.enabled:
            return False
        embed = {
            "title": "⚠️ 시스템 경고",
            "description": message[:500],
            "color": 0xFF4500,
        }
        return self._send({"embeds": [embed]})

    def _send(self, payload: dict) -> bool:
        """웹훅으로 페이로드를 전송한다. 최대 3회 재시도."""
        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed — cannot send Discord notification")
            return False

        max_retries = RETRY_DISCORD_WEBHOOK["max_retries"]
        wait_base = RETRY_DISCORD_WEBHOOK["wait_base"]
        wait_max = RETRY_DISCORD_WEBHOOK["wait_max"]

        for attempt in range(1, max_retries + 2):
            try:
                resp = httpx.post(
                    self._webhook_url,
                    json=payload,
                    timeout=10,
                )
                if resp.status_code in (200, 204):
                    logger.info(f"Discord notification sent (attempt {attempt})")
                    return True
                logger.warning(f"Discord HTTP {resp.status_code} on attempt {attempt}")
            except Exception as e:
                logger.warning(f"Discord send failed (attempt {attempt}): {e}")

            if attempt <= max_retries:
                wait = min(wait_base * (2 ** (attempt - 1)), wait_max)
                time.sleep(wait)

        logger.error(f"Discord notification failed after {max_retries + 1} attempts")
        return False
