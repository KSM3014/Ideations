"""리포트 생성기 — 일간/주간 리포트."""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import DASHBOARD_BATCHES_PATH
from logger import get_logger
from utils import atomic_json_write, kst_now, read_jsonl

logger = get_logger("report_generator")

OUTPUT_REPORTS = _PROJECT_ROOT / "output" / "reports"


class ReportGenerator:
    """일간/주간 리포트를 생성한다."""

    def __init__(self, batches_path: Path | str | None = None) -> None:
        self.batches_path = Path(batches_path) if batches_path else DASHBOARD_BATCHES_PATH

    def generate_daily(self, date_str: str | None = None) -> dict[str, Any]:
        """일간 리포트를 생성한다.

        Args:
            date_str: YYYY-MM-DD 형식. None이면 오늘.

        Returns:
            리포트 딕셔너리.
        """
        if date_str is None:
            date_str = kst_now().strftime("%Y-%m-%d")

        batches = read_jsonl(self.batches_path)
        daily = [b for b in batches if b.get("timestamp", "").startswith(date_str)]

        all_ideas = []
        for batch in daily:
            all_ideas.extend(batch.get("ideas", []))

        grade_dist = {}
        for idea in all_ideas:
            g = idea.get("grade", "?")
            grade_dist[g] = grade_dist.get(g, 0) + 1

        report = {
            "type": "daily",
            "date": date_str,
            "total_batches": len(daily),
            "total_ideas": len(all_ideas),
            "grade_distribution": grade_dist,
            "generated_at": kst_now().isoformat(),
        }

        # 저장
        OUTPUT_REPORTS.mkdir(parents=True, exist_ok=True)
        report_path = OUTPUT_REPORTS / f"daily_{date_str}.json"
        atomic_json_write(report_path, report)
        logger.info(f"Daily report generated: {report_path}")

        return report

    def generate_weekly(self) -> dict[str, Any]:
        """주간 리포트를 생성한다 (최근 7일)."""
        now = kst_now()
        dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        batches = read_jsonl(self.batches_path)
        weekly = [b for b in batches if any(b.get("timestamp", "").startswith(d) for d in dates)]

        all_ideas = []
        for batch in weekly:
            all_ideas.extend(batch.get("ideas", []))

        grade_dist = {}
        for idea in all_ideas:
            g = idea.get("grade", "?")
            grade_dist[g] = grade_dist.get(g, 0) + 1

        # 상위 아이디어 (점수 내림차순, 최대 10개)
        sorted_ideas = sorted(
            all_ideas,
            key=lambda x: x.get("weighted_score", x.get("numrv_score", 0)),
            reverse=True,
        )
        top_ideas = []
        for idea in sorted_ideas[:10]:
            top_ideas.append({
                "service_name": idea.get("service_name", ""),
                "grade": idea.get("grade", "?"),
                "score": idea.get("weighted_score", idea.get("numrv_score", 0)),
                "problem": idea.get("problem", "")[:100],
                "target": idea.get("target_buyer", idea.get("target", "")),
            })

        report = {
            "type": "weekly",
            "period_start": dates[-1],
            "period_end": dates[0],
            "total_batches": len(weekly),
            "total_ideas": len(all_ideas),
            "grade_distribution": grade_dist,
            "sa_count": grade_dist.get("S", 0) + grade_dist.get("A", 0),
            "top_ideas": top_ideas,
            "generated_at": kst_now().isoformat(),
        }

        OUTPUT_REPORTS.mkdir(parents=True, exist_ok=True)
        report_path = OUTPUT_REPORTS / f"weekly_{dates[0]}.json"
        atomic_json_write(report_path, report)
        logger.info(f"Weekly report generated: {report_path}")

        return report


# ──────────────────────────── CLI ────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="리포트 생성기")
    parser.add_argument("--type", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD (일간 전용)")
    args = parser.parse_args()

    gen = ReportGenerator()
    if args.type == "weekly":
        report = gen.generate_weekly()
    else:
        report = gen.generate_daily(args.date)

    print(json.dumps(report, ensure_ascii=False, indent=2))
