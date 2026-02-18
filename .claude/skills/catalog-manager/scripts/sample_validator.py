"""API 응답 샘플 검증기.

매칭된 API의 실제 응답을 확인하여 데이터 품질을 검증한다.
주간 배치에서 수행, 결과 캐시.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from logger import get_logger

logger = get_logger("sample_validator")


class SampleValidator:
    """API 응답 샘플 검증기."""

    def validate_api(self, api_id: str, endpoint_url: str) -> dict[str, Any]:
        """단일 API의 응답을 검증한다.

        Returns:
            {"api_id": ..., "valid": bool, "status_code": int, "sample_fields": [...]}
        """
        logger.info(f"Validating API {api_id}")
        # Stage 1에서 httpx 기반 구현 예정
        return {"api_id": api_id, "valid": False, "reason": "not_implemented"}

    def validate_batch(self, api_ids: list[str]) -> list[dict[str, Any]]:
        """복수 API를 배치 검증한다."""
        return [self.validate_api(aid, "") for aid in api_ids]
