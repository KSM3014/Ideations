"""메인 오케스트레이터 — 6-Phase 파이프라인 순차 실행.

Stage 0: IdeationEngine, TimeBudget, ClaudeCLIInvoker, PhaseResult.
Stage 9: 모든 Phase 메서드를 실제 스킬 스크립트에 연결.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# 프로젝트 루트를 sys.path에 추가 (scripts/ 에서 실행될 때)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 스킬 스크립트 경로 등록
_SKILL_PATHS = [
    _PROJECT_ROOT / ".claude" / "skills" / "signal-collector" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "api-matcher" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "market-validator" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "scorer" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "publisher" / "scripts",
    _PROJECT_ROOT / ".claude" / "skills" / "catalog-manager" / "scripts",
]
for p in _SKILL_PATHS:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import (
    ADAPTIVE_DEPTH,
    BASE_BUDGET_SEC,
    BUFFER_SEC,
    CLAUDE_CLI_CMD,
    CLAUDE_CLI_TIMEOUT_SEC,
    PHASE4_SIMPLIFY_THRESHOLD_SEC,
    PHASE4_SKIP_THRESHOLD_SEC,
    PROMPTS_DIR,
    RETRY_CLAUDE_CLI,
    TOTAL_BUDGET_SEC,
    VARIABLE_MAX_SEC,
    VARIABLE_POOL_SEC,
)
from logger import get_logger
from utils import generate_batch_id, kst_now, read_jsonl

logger = get_logger("run_engine")


# ──────────────────────────── PhaseResult 프로토콜 ────────────────────────────


@runtime_checkable
class PhaseResult(Protocol):
    """각 Phase 반환 타입이 준수해야 할 인터페이스."""

    batch_id: str
    duration_sec: float


# ──────────────────────────── TimeBudget ────────────────────────────


@dataclass
class TimeBudget:
    """시간 예산 추적기.

    - 기본 시간(고정) + 가변 공유 풀(24분) 관리.
    - 매 Phase 시작 시 잔여 풀을 계산하여 할당.
    - 적응형 깊이 판단 (Phase 4).
    """

    total_sec: int = TOTAL_BUDGET_SEC
    variable_pool_remaining: int = VARIABLE_POOL_SEC
    _started_at: float = field(default_factory=time.monotonic)
    _phase_starts: dict[int, float] = field(default_factory=dict)

    @property
    def elapsed_sec(self) -> float:
        return time.monotonic() - self._started_at

    @property
    def remaining_sec(self) -> float:
        return max(0.0, self.total_sec - self.elapsed_sec)

    def phase_budget(self, phase: int) -> float:
        """Phase에 할당 가능한 최대 시간(초)을 반환한다."""
        base = BASE_BUDGET_SEC.get(phase, 0)
        var_max = VARIABLE_MAX_SEC.get(phase, 0)
        var_alloc = min(var_max, self.variable_pool_remaining)
        return float(min(base + var_alloc, self.remaining_sec))

    def start_phase(self, phase: int) -> float:
        """Phase 시작을 기록하고 할당된 예산(초)을 반환한다."""
        self._phase_starts[phase] = time.monotonic()
        budget = self.phase_budget(phase)
        logger.info(
            f"Phase {phase} started — budget {budget:.0f}s, pool remaining {self.variable_pool_remaining}s",
            extra={"phase": phase},
        )
        return budget

    def end_phase(self, phase: int) -> float:
        """Phase 종료를 기록하고 소요 시간(초)을 반환한다. 초과분을 풀에서 차감."""
        start = self._phase_starts.get(phase)
        if start is None:
            return 0.0
        elapsed = time.monotonic() - start
        base = BASE_BUDGET_SEC.get(phase, 0)
        overshoot = max(0, elapsed - base)
        if overshoot > 0:
            deducted = min(int(overshoot), self.variable_pool_remaining)
            self.variable_pool_remaining -= deducted
            logger.info(
                f"Phase {phase} used {elapsed:.0f}s (+{overshoot:.0f}s over base), pool deducted {deducted}s → {self.variable_pool_remaining}s left",
                extra={"phase": phase, "duration_sec": elapsed},
            )
        else:
            logger.info(
                f"Phase {phase} completed in {elapsed:.0f}s (within base {base}s)",
                extra={"phase": phase, "duration_sec": elapsed},
            )
        return elapsed

    def adaptive_depth(self, hypothesis_count: int) -> str:
        """Phase 4 적응형 깊이 레벨을 결정한다."""
        remaining = self.remaining_sec

        if remaining < PHASE4_SKIP_THRESHOLD_SEC:
            return "skipped"
        if remaining < PHASE4_SIMPLIFY_THRESHOLD_SEC:
            return "simplified"
        if hypothesis_count <= ADAPTIVE_DEPTH["deep"]["max_hypotheses"]:
            return "deep"
        if hypothesis_count <= ADAPTIVE_DEPTH["standard"]["max_hypotheses"]:
            return "standard"
        return "light"


# ──────────────────────────── ClaudeCLIInvoker ────────────────────────────


class ClaudeCLIInvoker:
    """Claude CLI (`claude -p`) subprocess 호출 + JSON 파싱 + 지수 백오프 재시도."""

    def __init__(
        self,
        cmd: str = CLAUDE_CLI_CMD,
        timeout: int = CLAUDE_CLI_TIMEOUT_SEC,
        max_retries: int = RETRY_CLAUDE_CLI["max_retries"],
        wait_base: int = RETRY_CLAUDE_CLI["wait_base"],
        wait_max: int = RETRY_CLAUDE_CLI["wait_max"],
    ) -> None:
        self.cmd = cmd
        self.timeout = timeout
        self.max_retries = max_retries
        self.wait_base = wait_base
        self.wait_max = wait_max
        self._logger = get_logger("claude_cli")

    def invoke(self, prompt: str, *, phase: int | None = None) -> dict[str, Any]:
        """Claude CLI를 호출하고 JSON을 파싱하여 반환한다.

        최대 max_retries회 지수 백오프 재시도.
        모두 실패하면 RuntimeError를 발생시킨다.
        """
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 2):  # 1 + retries
            try:
                result = self._run_subprocess(prompt)
                parsed = self._extract_json(result)
                self._logger.info(
                    f"Claude CLI succeeded on attempt {attempt}",
                    extra={"phase": phase, "attempt": attempt},
                )
                return parsed
            except Exception as e:
                last_error = e
                self._logger.warning(
                    f"Claude CLI attempt {attempt} failed: {e}",
                    extra={"phase": phase, "attempt": attempt},
                )
                if attempt <= self.max_retries:
                    wait = min(self.wait_base * (2 ** (attempt - 1)), self.wait_max)
                    self._logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)

        # 모든 재시도 실패 → 에스컬레이션
        self._logger.error(
            f"Claude CLI exhausted all {self.max_retries + 1} attempts — escalating",
            extra={"phase": phase, "trigger": "escalation"},
        )
        raise RuntimeError(
            f"Claude CLI failed after {self.max_retries + 1} attempts: {last_error}"
        )

    def _run_subprocess(self, prompt: str) -> str:
        """claude -p 를 subprocess로 실행하고 stdout을 반환한다."""
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # 중첩 세션 방지 우회
        proc = subprocess.run(
            [self.cmd, "-p", prompt],
            capture_output=True,
            timeout=self.timeout,
            shell=(sys.platform == "win32"),  # Windows: .cmd 파일 실행 필요
            env=env,
        )
        # Windows cp949 / Linux utf-8 안전 디코딩
        def _decode(data: bytes) -> str:
            if not data:
                return ""
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("cp949", errors="replace")

        stdout = _decode(proc.stdout)
        stderr = _decode(proc.stderr)
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p exited with code {proc.returncode}: {stderr[:500]}")
        return stdout

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        """Claude CLI 출력에서 JSON을 추출한다. 마크다운 펜스 제거."""
        # ```json ... ``` 패턴 제거
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # JSON 객체/배열 시작 위치 찾기
        for i, ch in enumerate(cleaned):
            if ch in ("{", "["):
                break
        else:
            raise ValueError(f"No JSON found in Claude CLI output (first 200 chars): {raw[:200]}")

        try:
            return json.loads(cleaned[i:])
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse error: {e}\nRaw (first 300 chars): {cleaned[i:i+300]}")


# ──────────────────────────── IdeationEngine ────────────────────────────


class _DryRunClaude:
    """드라이런 모드용 모의 Claude CLI — JSON 고정 응답 반환."""

    def invoke(self, prompt: str, *, phase: int | None = None) -> dict | list:
        import random
        if phase == 2:
            return {"hypotheses": [
                {
                    "id": f"H-{i+1:03d}",
                    "service_name": f"드라이런 서비스 #{i+1}",
                    "problem": "드라이런 문제 정의",
                    "solution": "드라이런 솔루션",
                    "target_buyer": random.choice(["지자체", "시민", "연구기관", "기업"]),
                    "revenue_model": random.choice(["SaaS", "API 과금", "광고", "프리미엄"]),
                    "opportunity_area": "드라이런 영역",
                    "data_needs": [{"field_name": "테스트필드", "description": "테스트", "priority": "필수"}],
                }
                for i in range(5)
            ]}
        elif phase == 4:
            return {
                "timing_fit": round(random.uniform(0.3, 0.9), 2),
                "revenue_reference": round(random.uniform(0.3, 0.9), 2),
                "mvp_difficulty": round(random.uniform(0.3, 0.9), 2),
            }
        elif phase == 5:
            return [
                {"id": f"H-{i+1:03d}", "N": random.randint(2, 5), "U": random.randint(2, 5),
                 "M": random.randint(2, 5), "R": random.randint(2, 5)}
                for i in range(5)
            ]
        return {}


class IdeationEngine:
    """6-Phase 파이프라인 오케스트레이터."""

    def __init__(self, manual_signals: str | None = None, dry_run: bool = False) -> None:
        self.batch_id = generate_batch_id()
        self.budget = TimeBudget()
        self.claude = _DryRunClaude() if dry_run else ClaudeCLIInvoker()
        self._manual_signals = manual_signals
        self._logger = get_logger("engine")

    def run(self) -> dict[str, Any]:
        """전체 파이프라인을 순차 실행한다."""
        self._logger.info(f"Pipeline started — batch {self.batch_id}")
        started_at = kst_now()
        result: dict[str, Any] = {
            "batch_id": self.batch_id,
            "started_at": started_at.isoformat(),
            "phases": {},
            "success": False,
            "error": None,
        }

        try:
            # Phase 1: 맥락 수집
            p1 = self._phase1()
            result["phases"]["phase1"] = p1

            # Phase 2: 가설 생성
            p2 = self._phase2(p1)
            result["phases"]["phase2"] = p2

            # Phase 3: API 매칭
            p3 = self._phase3(p2)
            result["phases"]["phase3"] = p3

            # Phase 4: 시장 검증
            p4 = self._phase4(p3)
            result["phases"]["phase4"] = p4

            # Phase 5: 스코어링
            p5 = self._phase5(p4)
            result["phases"]["phase5"] = p5

            # Phase 6: 발행
            p6 = self._phase6(p5)
            result["phases"]["phase6"] = p6

            result["success"] = True

        except Exception as e:
            self._logger.error(f"Pipeline failed: {e}", exc_info=True)
            result["error"] = str(e)

        result["finished_at"] = kst_now().isoformat()
        result["total_duration_sec"] = self.budget.elapsed_sec
        self._logger.info(
            f"Pipeline finished — success={result['success']}, duration={result['total_duration_sec']:.0f}s"
        )
        return result

    # ── Phase 1: 맥락 수집 ──

    def _phase1(self) -> dict[str, Any]:
        """Phase 1: 신호 수집 — signal_aggregator 사용."""
        self.budget.start_phase(1)

        if self._manual_signals:
            self._logger.info(f"Phase 1: manual signals provided — skipping crawlers")
            signals = [
                {
                    "source": "manual",
                    "title": self._manual_signals,
                    "url": "",
                    "snippet": self._manual_signals,
                    "collected_at": kst_now().isoformat(),
                }
            ]
        else:
            try:
                from signal_aggregator import collect_signals

                signals = asyncio.run(collect_signals())
                self._logger.info(f"Phase 1: collected {len(signals)} signals")
            except Exception as e:
                self._logger.warning(f"Phase 1: signal collection failed, continuing with empty — {e}")
                signals = []

        elapsed = self.budget.end_phase(1)
        return {"batch_id": self.batch_id, "signals": signals, "duration_sec": elapsed}

    # ── Phase 2: 가설 생성 ──

    def _phase2(self, phase1_result: dict) -> dict[str, Any]:
        """Phase 2: Claude CLI로 가설 생성."""
        self.budget.start_phase(2)

        signals = phase1_result.get("signals", [])

        # 프롬프트 템플릿 로드
        prompt_path = PROMPTS_DIR / "phase2_hypothesis.md"
        prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

        # 도메인 요약 로드 (카탈로그가 있는 경우)
        domain_summary = ""
        try:
            from catalog_store import CatalogStore

            store = CatalogStore()
            summaries = store.get_domain_summaries()
            if summaries:
                domain_summary = json.dumps(summaries, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 최근 아카이브 로드 (중복 회피)
        recent_archive = ""
        try:
            from archive_manager import ArchiveManager

            mgr = ArchiveManager()
            recent_names = mgr.get_service_names(hours=24)
            if recent_names:
                recent_archive = json.dumps(recent_names, ensure_ascii=False)
        except Exception:
            pass

        # 피드백 요약 로드
        feedback_summary = ""
        try:
            from config import FEEDBACK_PATH

            feedback_records = read_jsonl(FEEDBACK_PATH)
            if feedback_records:
                blacklisted = [r["hypothesis_id"] for r in feedback_records if r.get("action") == "blacklist"]
                liked = [r["hypothesis_id"] for r in feedback_records if r.get("action") == "like"]
                feedback_summary = json.dumps(
                    {"blacklisted": blacklisted[-20:], "liked": liked[-20:]},
                    ensure_ascii=False,
                )
        except Exception:
            pass

        # 프롬프트 조립
        signals_text = json.dumps(signals[:30], ensure_ascii=False, indent=2)
        full_prompt = (
            f"{prompt_template}\n\n"
            f"## 입력 데이터\n\n"
            f"### 외부 신호 (최근 수집)\n```json\n{signals_text}\n```\n\n"
            f"### 카탈로그 도메인 요약\n```json\n{domain_summary or '[]'}\n```\n\n"
            f"### 최근 24h 아카이브 (중복 회피)\n{recent_archive or '없음'}\n\n"
            f"### 피드백 요약\n{feedback_summary or '없음'}\n"
        )

        # Claude CLI 호출
        raw_result = self.claude.invoke(full_prompt, phase=2)

        # 결과에서 가설 추출
        hypotheses = raw_result.get("hypotheses", [])

        # 가설 ID 부여
        for i, h in enumerate(hypotheses):
            if not h.get("id"):
                h["id"] = f"H-{i + 1:03d}"

        self._logger.info(f"Phase 2: generated {len(hypotheses)} hypotheses")

        elapsed = self.budget.end_phase(2)
        return {
            "batch_id": self.batch_id,
            "hypotheses": hypotheses,
            "signal_count": len(signals),
            "duration_sec": elapsed,
        }

    # ── Phase 3: API 매칭 ──

    def _phase3(self, phase2_result: dict) -> dict[str, Any]:
        """Phase 3: 의미적 매칭 + 조인 분석 + 적합도 계산."""
        self.budget.start_phase(3)

        hypotheses = phase2_result.get("hypotheses", [])

        from feasibility import FeasibilityCalculator
        from join_analyzer import JoinAnalyzer
        from semantic_matcher import SemanticMatcher

        matcher = SemanticMatcher()
        join_analyzer = JoinAnalyzer()
        feasibility_calc = FeasibilityCalculator()

        matches = []
        passed_count = 0

        for hyp in hypotheses:
            hyp_id = hyp.get("id", "")
            data_needs = hyp.get("data_needs", [])

            # 의미적 매칭
            match_result = matcher.match_hypothesis(hyp)
            unique_apis = match_result.get("unique_apis", [])

            # 조인 키 분석
            join_pairs = join_analyzer.analyze_api_pairs(
                [{"api_id": a["api_id"], "params": []} for a in unique_apis]
            )
            join_key_count = sum(len(jp.get("join_keys", [])) for jp in join_pairs)

            # 적합도 계산
            matched_needs = sum(
                1 for m in match_result.get("matches_by_need", [])
                if m.get("matched_apis")
            )
            feasibility = feasibility_calc.calculate(
                total_data_needs=len(data_needs),
                matched_data_needs=matched_needs,
                matched_api_count=len(unique_apis),
                join_key_count=join_key_count,
            )

            match_entry = {
                "hypothesis_id": hyp_id,
                "matched_apis": unique_apis[:10],
                "join_pairs": join_pairs,
                "feasibility_pct": feasibility["feasibility_pct"],
                "passed": feasibility["passed"],
            }
            matches.append(match_entry)

            if feasibility["passed"]:
                passed_count += 1
                hyp["matched_apis"] = unique_apis[:10]
                hyp["feasibility_pct"] = feasibility["feasibility_pct"]

        self._logger.info(
            f"Phase 3: {passed_count}/{len(hypotheses)} hypotheses passed feasibility gate"
        )

        elapsed = self.budget.end_phase(3)
        return {
            "batch_id": self.batch_id,
            "matches": matches,
            "passed_count": passed_count,
            "passed_hypotheses": [h for h in hypotheses if h.get("feasibility_pct")],
            "duration_sec": elapsed,
        }

    # ── Phase 4: 시장 검증 ──

    def _phase4(self, phase3_result: dict) -> dict[str, Any]:
        """Phase 4: 경쟁사 검색 + 프록시 스코어 + 검증 점수 산출."""
        self.budget.start_phase(4)

        passed_hypotheses = phase3_result.get("passed_hypotheses", [])
        hypothesis_count = len(passed_hypotheses)
        depth = self.budget.adaptive_depth(hypothesis_count)
        self._logger.info(f"Phase 4: depth={depth}, hypotheses={hypothesis_count}")

        if depth == "skipped":
            self._logger.warning("Phase 4 skipped — remaining time < 5min, V=3 assigned")
            for hyp in passed_hypotheses:
                hyp["validation_score"] = None
                hyp["validation_passed"] = True
                hyp["default_v"] = 3
            elapsed = self.budget.end_phase(4)
            return {
                "batch_id": self.batch_id,
                "validations": passed_hypotheses,
                "skipped": True,
                "default_v": 3,
                "duration_sec": elapsed,
            }

        from competitor_search import CompetitorSearcher
        from market_proxy_scorer import MarketProxyScorer
        from validation_scorer import ValidationScorer

        competitor_searcher = CompetitorSearcher()
        proxy_scorer = MarketProxyScorer()
        validation_scorer = ValidationScorer()

        validations = []

        for hyp in passed_hypotheses:
            service_name = hyp.get("service_name", "")

            # 경쟁사 검색 (비동기)
            try:
                competitors = asyncio.run(competitor_searcher.search(service_name))
            except Exception as e:
                self._logger.warning(f"Competitor search failed for '{service_name}': {e}")
                competitors = []

            # 시장 프록시 스코어 — 가설 기반 동적 추정
            target = hyp.get("target_buyer", "")
            community_size = "large" if any(
                kw in target for kw in ("공공", "전국", "정부", "지자체", "시민", "국민")
            ) else "small" if any(
                kw in target for kw in ("연구", "전문", "특정", "니치")
            ) else "medium"

            comp_count = len(competitors)
            search_trend = (
                "rising" if comp_count >= 5 else
                "stable" if comp_count >= 2 else
                "declining"
            )

            proxy_score = proxy_scorer.score({
                "similar_services_count": comp_count,
                "target_community_size": community_size,
                "search_trend": search_trend,
            })

            # Claude CLI로 추가 검증 (deep/standard 모드만)
            timing_fit = 0.5
            revenue_reference = 0.5
            mvp_difficulty = 0.5

            if depth in ("deep", "standard"):
                try:
                    prompt_path = PROMPTS_DIR / "phase4_validation.md"
                    prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

                    validation_prompt = (
                        f"{prompt_template}\n\n"
                        f"## 검증 대상\n"
                        f"- 서비스: {service_name}\n"
                        f"- 문제: {hyp.get('problem', '')}\n"
                        f"- 솔루션: {hyp.get('solution', '')}\n"
                        f"- 타깃: {hyp.get('target_buyer', '')}\n"
                        f"- 수익 모델: {hyp.get('revenue_model', '')}\n"
                        f"- 경쟁사 수: {len(competitors)}개\n"
                        f"\n응답은 JSON으로: "
                        f'{{"timing_fit": 0.0~1.0, "revenue_reference": 0.0~1.0, "mvp_difficulty": 0.0~1.0}}'
                    )
                    validation_raw = self.claude.invoke(validation_prompt, phase=4)
                    timing_fit = float(validation_raw.get("timing_fit", 0.5))
                    revenue_reference = float(validation_raw.get("revenue_reference", 0.5))
                    mvp_difficulty = float(validation_raw.get("mvp_difficulty", 0.5))
                except Exception as e:
                    self._logger.warning(f"Claude validation failed for '{service_name}', using defaults: {e}")

            # 종합 검증 점수
            validation_result = validation_scorer.calculate(
                hypothesis_data={
                    "timing_fit": timing_fit,
                    "revenue_reference": revenue_reference,
                    "mvp_difficulty": mvp_difficulty,
                },
                competitors=competitors,
                proxy_score=proxy_score,
            )

            hyp["validation_score"] = validation_result["total_score"]
            hyp["validation_passed"] = validation_result["passed"]
            hyp["validation_breakdown"] = validation_result["breakdown"]
            hyp["competitors_count"] = len(competitors)
            validations.append(hyp)

        passed_validations = [v for v in validations if v.get("validation_passed")]
        self._logger.info(
            f"Phase 4: {len(passed_validations)}/{len(validations)} passed validation gate"
        )

        elapsed = self.budget.end_phase(4)
        return {
            "batch_id": self.batch_id,
            "validations": passed_validations,
            "total_validated": len(validations),
            "passed_count": len(passed_validations),
            "skipped": False,
            "duration_sec": elapsed,
        }

    # ── Phase 5: 스코어링 ──

    def _phase5(self, phase4_result: dict) -> dict[str, Any]:
        """Phase 5: NUMR-V 스코어링 + 중복제거 + 등급 분류."""
        self.budget.start_phase(5)

        validations = phase4_result.get("validations", [])
        is_skipped = phase4_result.get("skipped", False)
        default_v = phase4_result.get("default_v")

        from dedup_engine import DedupEngine
        from grade_classifier import GradeClassifier
        from numrv_scorer import NUMRVScorer

        scorer = NUMRVScorer()
        dedup = DedupEngine()
        grader = GradeClassifier()

        # Claude CLI로 NUMR 상대 평가 (배치 전체)
        if validations:
            try:
                prompt_path = PROMPTS_DIR / "phase5_scoring.md"
                prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

                ideas_summary = []
                for v in validations:
                    ideas_summary.append({
                        "id": v.get("id", ""),
                        "service_name": v.get("service_name", ""),
                        "problem": v.get("problem", ""),
                        "solution": v.get("solution", ""),
                        "target_buyer": v.get("target_buyer", ""),
                        "feasibility_pct": v.get("feasibility_pct", 0),
                        "validation_score": v.get("validation_score"),
                    })

                scoring_prompt = (
                    f"{prompt_template}\n\n"
                    f"## 평가 대상 아이디어 배치\n"
                    f"```json\n{json.dumps(ideas_summary, ensure_ascii=False, indent=2)}\n```\n\n"
                    f"각 아이디어에 N, U, M, R 점수(1~5)를 JSON 배열로 출력하세요:\n"
                    f'[{{"id": "H-001", "N": 3, "U": 4, "M": 3, "R": 4}}, ...]'
                )
                numr_raw = self.claude.invoke(scoring_prompt, phase=5)

                # 결과 매핑
                if isinstance(numr_raw, list):
                    numr_map = {item["id"]: item for item in numr_raw if isinstance(item, dict)}
                elif isinstance(numr_raw, dict) and "scores" in numr_raw:
                    numr_map = {item["id"]: item for item in numr_raw["scores"] if isinstance(item, dict)}
                else:
                    numr_map = {}

                for v in validations:
                    vid = v.get("id", "")
                    numr = numr_map.get(vid, {})
                    v_score = default_v if is_skipped else (v.get("validation_score", 50) / 20)
                    v["scores"] = {
                        "N": float(numr.get("N", 3)),
                        "U": float(numr.get("U", 3)),
                        "M": float(numr.get("M", 3)),
                        "R": float(numr.get("R", 3)),
                        "V": min(float(v_score), 5.0),
                    }

            except Exception as e:
                self._logger.warning(f"Phase 5 Claude scoring failed, using heuristic defaults: {e}")
                for v in validations:
                    v_score = default_v if is_skipped else (v.get("validation_score", 50) / 20)
                    # 휴리스틱 기반 점수 — Claude 실패 시에도 차별화
                    feas = v.get("feasibility_pct", 50)
                    val = v.get("validation_score", 50)
                    comp = v.get("competitors_count", 0)
                    n_score = max(1, min(5, 5 - (comp * 0.5)))           # 경쟁 적을수록 참신
                    u_score = max(1, min(5, val / 20))                    # 검증 높을수록 긴급
                    m_score = max(1, min(5, 1 + (comp * 0.6)))           # 경쟁 존재 = 시장 존재
                    r_score = max(1, min(5, feas / 20))                   # 적합도 높을수록 실현 가능
                    v["scores"] = {
                        "N": round(n_score, 1), "U": round(u_score, 1),
                        "M": round(m_score, 1), "R": round(r_score, 1),
                        "V": min(float(v_score), 5.0),
                    }

        # NUMR-V 가중 점수
        scored = scorer.score_batch(validations)

        # 중복제거 (임베딩이 있는 경우만)
        scored = dedup.check_duplicates(scored)
        unique_ideas = [s for s in scored if not s.get("is_duplicate", False)]

        # 등급 분류
        graded = grader.classify(unique_ideas)

        self._logger.info(
            f"Phase 5: {len(graded)} ideas graded "
            f"(from {len(validations)} validated, {len(validations) - len(unique_ideas)} duplicates removed)"
        )

        elapsed = self.budget.end_phase(5)
        return {
            "batch_id": self.batch_id,
            "scored_ideas": graded,
            "total_scored": len(scored),
            "duplicates_removed": len(scored) - len(unique_ideas),
            "duration_sec": elapsed,
        }

    # ── Phase 6: 발행 ──

    def _phase6(self, phase5_result: dict) -> dict[str, Any]:
        """Phase 6: 대시보드 기록 + Discord 알림 + 아카이브."""
        self.budget.start_phase(6)

        scored_ideas = phase5_result.get("scored_ideas", [])

        from archive_manager import ArchiveManager
        from dashboard_writer import DashboardWriter
        from discord_notifier import DiscordNotifier

        writer = DashboardWriter()
        notifier = DiscordNotifier()
        archiver = ArchiveManager()

        # 대시보드 기록
        dashboard_ok = writer.write_batch(self.batch_id, scored_ideas)

        # Discord 알림 (S/A급만)
        notified = 0
        for idea in scored_ideas:
            grade = idea.get("grade", "")
            if grade in ("S", "A"):
                if notifier.notify_idea(idea):
                    notified += 1

        # 아카이브
        archived = archiver.archive_ideas(self.batch_id, scored_ideas)

        self._logger.info(
            f"Phase 6: dashboard={'OK' if dashboard_ok else 'FAIL'}, "
            f"notified={notified}, archived={archived}"
        )

        elapsed = self.budget.end_phase(6)
        return {
            "batch_id": self.batch_id,
            "publish": {
                "dashboard_written": dashboard_ok,
                "discord_notified": notified,
                "ideas_archived": archived,
                "total_ideas": len(scored_ideas),
            },
            "duration_sec": elapsed,
        }


# ──────────────────────────── CLI 엔트리포인트 ────────────────────────────


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="API Ideation Engine v6.0")
    parser.add_argument("--manual-signals", type=str, help="수동 신호 텍스트 (Phase 1 스킵)")
    parser.add_argument("--dry-run", action="store_true", help="Claude CLI 모킹 (테스트용)")
    args = parser.parse_args()

    engine = IdeationEngine(manual_signals=args.manual_signals, dry_run=args.dry_run)
    result = engine.run()

    # 결과 출력
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
