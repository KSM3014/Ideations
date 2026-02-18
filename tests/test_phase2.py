"""MVP 게이트 테스트 #6~7 — Claude CLI 파싱/재시도, Phase 2 출력 Pydantic 검증."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.run_engine import ClaudeCLIInvoker
from server.schemas.api_contracts import Phase2Output, Hypothesis


VALID_PHASE2_JSON = json.dumps({
    "schema_version": "1.0",
    "hypotheses": [
        {
            "id": "H-001",
            "service_name": "스마트 교통 알리미",
            "problem": "실시간 교통 정보 접근성 부족",
            "solution": "공공 교통 API 기반 대시보드",
            "target_buyer": "지자체 교통과",
            "revenue_model": "SaaS 구독",
            "opportunity_area": "스마트시티",
            "data_needs": [
                {"field_name": "교통량", "description": "시간대별 교통량", "priority": "필수"}
            ],
            "api_suggestions": [
                {"api_name": "실시간 교통량 API", "reason": "실시간 교통량 데이터 제공"}
            ],
        }
    ],
})


class TestClaudeCLIInvoker:
    """테스트 #6: Claude CLI 파싱 실패 → 지수 백오프 재시도(2회) → 에스컬레이션."""

    def test_success_on_first_attempt(self):
        invoker = ClaudeCLIInvoker(max_retries=2, wait_base=0, wait_max=0)
        with patch.object(invoker, "_run_subprocess", return_value=VALID_PHASE2_JSON):
            result = invoker.invoke("test prompt", phase=2)
        assert "hypotheses" in result

    def test_success_on_retry(self):
        """첫 번째 실패 → 두 번째 성공."""
        invoker = ClaudeCLIInvoker(max_retries=2, wait_base=0, wait_max=0)
        call_count = 0

        def side_effect(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "invalid json output"
            return VALID_PHASE2_JSON

        with patch.object(invoker, "_run_subprocess", side_effect=side_effect):
            result = invoker.invoke("test", phase=2)

        assert call_count == 2
        assert "hypotheses" in result

    def test_exhausted_retries_raises(self):
        """3회 모두 실패 → RuntimeError 에스컬레이션."""
        invoker = ClaudeCLIInvoker(max_retries=2, wait_base=0, wait_max=0)
        with patch.object(invoker, "_run_subprocess", return_value="not json"):
            with pytest.raises(RuntimeError, match="failed after 3 attempts"):
                invoker.invoke("test", phase=2)

    def test_retry_count_matches_config(self):
        """정확히 max_retries + 1 회 호출."""
        invoker = ClaudeCLIInvoker(max_retries=2, wait_base=0, wait_max=0)
        mock_fn = MagicMock(return_value="bad output")
        with patch.object(invoker, "_run_subprocess", mock_fn):
            with pytest.raises(RuntimeError):
                invoker.invoke("test", phase=2)
        assert mock_fn.call_count == 3  # 1 initial + 2 retries


class TestJsonExtraction:
    """JSON 추출 테스트 — 마크다운 펜스 제거 등."""

    def test_plain_json(self):
        raw = '{"key": "value"}'
        result = ClaudeCLIInvoker._extract_json(raw)
        assert result["key"] == "value"

    def test_markdown_fenced_json(self):
        raw = '```json\n{"key": "value"}\n```'
        result = ClaudeCLIInvoker._extract_json(raw)
        assert result["key"] == "value"

    def test_text_before_json(self):
        raw = 'Here is the result:\n\n{"key": "value"}'
        result = ClaudeCLIInvoker._extract_json(raw)
        assert result["key"] == "value"

    def test_no_json_raises(self):
        raw = "This is just plain text without any JSON"
        with pytest.raises(ValueError, match="No JSON found"):
            ClaudeCLIInvoker._extract_json(raw)

    def test_array_json(self):
        raw = '[{"a": 1}, {"b": 2}]'
        result = ClaudeCLIInvoker._extract_json(raw)
        assert isinstance(result, list)
        assert len(result) == 2


class TestPhase2PydanticValidation:
    """테스트 #7: Phase 2 출력 Pydantic 검증 통과/실패."""

    def test_valid_output_passes(self):
        data = json.loads(VALID_PHASE2_JSON)
        # Phase2Output에 batch_id 추가
        data["batch_id"] = "test-batch"
        output = Phase2Output.model_validate(data)
        assert len(output.hypotheses) == 1
        assert output.hypotheses[0].service_name == "스마트 교통 알리미"

    def test_missing_required_field_fails(self):
        data = {
            "batch_id": "test",
            "hypotheses": [
                {
                    "id": "H-001",
                    # service_name 누락
                    "problem": "문제",
                    "solution": "솔루션",
                    "target_buyer": "타깃",
                    "revenue_model": "모델",
                }
            ],
        }
        with pytest.raises(Exception):  # ValidationError
            Phase2Output.model_validate(data)

    def test_empty_hypotheses_valid(self):
        data = {"batch_id": "test", "hypotheses": []}
        output = Phase2Output.model_validate(data)
        assert len(output.hypotheses) == 0
