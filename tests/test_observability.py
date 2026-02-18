"""2차 확장 테스트 — SLI/SLO 관측 가능성 (config.SLO, BASE_BUDGET_SEC 기반 계산)."""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import BASE_BUDGET_SEC, SLO


class TestHourlySuccessRate:
    """SLI: 시간당 성공률 계산 및 SLO 비교."""

    def test_hourly_success_rate_calculation(self, tmp_path):
        """10건 로그 중 8건 성공(80%) → SLO 95% 미달 확인."""
        log_path = tmp_path / "run_log.jsonl"

        # 10건 로그 기록: 8 성공, 2 실패
        records = []
        for i in range(8):
            records.append({"batch_id": f"B-{i:03d}", "success": True})
        for i in range(2):
            records.append({"batch_id": f"B-F{i:03d}", "success": False})

        with open(log_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # 로그 읽기 및 성공률 계산
        with open(log_path, "r", encoding="utf-8") as f:
            loaded = [json.loads(line.strip()) for line in f if line.strip()]

        total = len(loaded)
        successes = sum(1 for r in loaded if r.get("success") is True)
        success_rate = successes / total  # 8/10 = 0.80

        assert total == 10
        assert successes == 8
        assert success_rate == pytest.approx(0.80)

        # SLO 비교: 0.80 < 0.95 → 미달
        slo_target = SLO["hourly_success_rate"]
        assert slo_target == 0.95
        assert success_rate < slo_target, "성공률 80%는 SLO 95% 미달"


class TestPhaseTimeoutDetection:
    """SLI: Phase별 타임아웃 초과 감지."""

    def test_phase_timeout_detection(self):
        """Phase 2 기본 예산(600s) 초과 여부 감지 — 700만 초과."""
        phase2_base = BASE_BUDGET_SEC[2]  # 600초 (10분)
        assert phase2_base == 600

        durations = [280, 310, 700, 290]

        # 기본 예산 초과 건 필터
        exceeded = [d for d in durations if d > phase2_base]

        # 700만 초과
        assert exceeded == [700]
        assert len(exceeded) == 1

        # 초과하지 않은 건들 확인
        within_budget = [d for d in durations if d <= phase2_base]
        assert len(within_budget) == 3
        assert all(d <= phase2_base for d in within_budget)
