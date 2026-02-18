"""Pydantic 모델 — Phase 1~6 입출력 + API 요청/응답 스키마.

schema_version 필드를 포함하여 DB 마이그레이션 시 버전 비교에 사용한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


# ──────────────────────────── 공통 ────────────────────────────


class BaseSchema(BaseModel):
    schema_version: str = Field(default=SCHEMA_VERSION, description="스키마 버전")


# ──────────────────────────── Phase 1: 신호 수집 ────────────────────────────


class SignalItem(BaseModel):
    source: str = Field(description="신호 소스 (google_trends, news, tech, policy, funding)")
    title: str = Field(description="신호 제목")
    url: str | None = Field(default=None, description="출처 URL")
    snippet: str = Field(default="", description="요약 텍스트")
    collected_at: datetime = Field(description="수집 시각 (KST)")


class Phase1Output(BaseSchema):
    batch_id: str = Field(description="배치 ID")
    signals: list[SignalItem] = Field(default_factory=list)
    sources_attempted: list[str] = Field(default_factory=list)
    sources_succeeded: list[str] = Field(default_factory=list)
    duration_sec: float = Field(default=0.0)


# ──────────────────────────── Phase 2: 가설 생성 ────────────────────────────


class DataNeed(BaseModel):
    field_name: str = Field(description="필요 데이터 필드명")
    description: str = Field(default="", description="데이터 설명")
    priority: Literal["필수", "선택"] = Field(default="필수")


class ApiSuggestion(BaseModel):
    api_name: str = Field(description="예비 매칭 API 이름")
    reason: str = Field(default="", description="매칭 근거")


class Hypothesis(BaseModel):
    id: str = Field(description="가설 고유 ID (e.g., H-001)")
    service_name: str = Field(description="서비스명")
    problem: str = Field(description="문제 정의")
    solution: str = Field(description="솔루션 컨셉")
    target_buyer: str = Field(description="타깃 구매자")
    revenue_model: str = Field(description="수익 모델")
    opportunity_area: str = Field(default="", description="기회 영역")
    data_needs: list[DataNeed] = Field(default_factory=list)
    api_suggestions: list[ApiSuggestion] = Field(default_factory=list)


class Phase2Output(BaseSchema):
    batch_id: str
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    retry_count: int = Field(default=0)
    duration_sec: float = Field(default=0.0)


# ──────────────────────────── Phase 3: API 매칭 ────────────────────────────


class MatchedApi(BaseModel):
    api_id: str = Field(description="카탈로그 API ID")
    api_name: str = Field(description="API 이름")
    relevance_score: float = Field(description="의미적 유사도 점수 (0~1)")
    matched_fields: list[str] = Field(default_factory=list, description="매칭된 데이터 필드")


class JoinKey(BaseModel):
    key_name: str = Field(description="조인 키 이름 (e.g., 시군구코드)")
    api_pair: list[str] = Field(description="조인 가능한 API 쌍")


class HypothesisMatch(BaseModel):
    hypothesis_id: str
    matched_apis: list[MatchedApi] = Field(default_factory=list)
    join_keys: list[JoinKey] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    feasibility_pct: float = Field(description="적합도 % (0~100)")
    passed: bool = Field(description="품질 게이트 통과 여부 (≥ 40%)")


class Phase3Output(BaseSchema):
    batch_id: str
    matches: list[HypothesisMatch] = Field(default_factory=list)
    total_hypotheses: int = Field(default=0)
    passed_count: int = Field(default=0)
    duration_sec: float = Field(default=0.0)


# ──────────────────────────── Phase 4: 시장 검증 ────────────────────────────


class CompetitorInfo(BaseModel):
    name: str
    url: str | None = None
    differentiation: str = Field(default="", description="차별화 포인트")


class ValidationScores(BaseModel):
    competitor_analysis: float = Field(ge=0, le=25, description="경쟁사 분석 (0~25)")
    market_demand_proxy: float = Field(ge=0, le=25, description="시장 수요 프록시 (0~25)")
    timing_fit: float = Field(ge=0, le=20, description="타이밍 적합성 (0~20)")
    revenue_reference: float = Field(ge=0, le=15, description="수익화 사례 (0~15)")
    mvp_difficulty: float = Field(ge=0, le=15, description="MVP 난이도 (0~15)")

    @property
    def total(self) -> float:
        return (
            self.competitor_analysis
            + self.market_demand_proxy
            + self.timing_fit
            + self.revenue_reference
            + self.mvp_difficulty
        )


class HypothesisValidation(BaseModel):
    hypothesis_id: str
    competitors: list[CompetitorInfo] = Field(default_factory=list)
    scores: ValidationScores
    total_score: float = Field(description="검증 총점 (0~100)")
    passed: bool = Field(description="품질 게이트 통과 여부 (≥ 50)")
    depth_mode: Literal["deep", "standard", "light", "simplified", "skipped"] = Field(
        default="standard"
    )


class Phase4Output(BaseSchema):
    batch_id: str
    validations: list[HypothesisValidation] = Field(default_factory=list)
    total_validated: int = Field(default=0)
    passed_count: int = Field(default=0)
    duration_sec: float = Field(default=0.0)


# ──────────────────────────── Phase 5: 스코어링 ────────────────────────────


class NUMRVScores(BaseModel):
    N: float = Field(ge=1, le=5, description="Novelty (1~5)")
    U: float = Field(ge=1, le=5, description="Urgency (1~5)")
    M: float = Field(ge=1, le=5, description="Market Demand (1~5)")
    R: float = Field(ge=1, le=5, description="Revenue (1~5)")
    V: float = Field(ge=1, le=5, description="Validation (1~5)")


class ScoredIdea(BaseModel):
    hypothesis_id: str
    service_name: str
    numrv: NUMRVScores
    weighted_score: float = Field(description="가중합 점수")
    grade: Literal["S", "A", "B", "C", "D"]
    is_duplicate: bool = Field(default=False, description="24h 중복 여부")
    duplicate_of: str | None = Field(default=None, description="중복 대상 ID")


class Phase5Output(BaseSchema):
    batch_id: str
    scored_ideas: list[ScoredIdea] = Field(default_factory=list)
    deduplicated_count: int = Field(default=0)
    duration_sec: float = Field(default=0.0)


# ──────────────────────────── Phase 6: 발행 ────────────────────────────


class PublishResult(BaseModel):
    dashboard_updated: bool = Field(default=False)
    discord_sent: bool = Field(default=False)
    discord_notified_grades: list[str] = Field(default_factory=list)
    archive_appended: int = Field(default=0)
    report_path: str | None = None


class Phase6Output(BaseSchema):
    batch_id: str
    publish: PublishResult = Field(default_factory=PublishResult)
    duration_sec: float = Field(default=0.0)


# ──────────────────────────── 파이프라인 전체 결과 ────────────────────────────


class PipelineResult(BaseSchema):
    batch_id: str
    started_at: datetime
    finished_at: datetime | None = None
    total_duration_sec: float = Field(default=0.0)
    phase1: Phase1Output | None = None
    phase2: Phase2Output | None = None
    phase3: Phase3Output | None = None
    phase4: Phase4Output | None = None
    phase5: Phase5Output | None = None
    phase6: Phase6Output | None = None
    success: bool = Field(default=False)
    error: str | None = None


# ──────────────────────────── API 서버 ────────────────────────────


class BatchSummary(BaseModel):
    batch_id: str
    timestamp: datetime
    total_ideas: int
    grade_distribution: dict[str, int] = Field(default_factory=dict)


class IdeaDetail(BaseModel):
    hypothesis_id: str
    batch_id: str
    service_name: str
    problem: str
    solution: str
    target_buyer: str
    revenue_model: str
    grade: str
    weighted_score: float
    numrv: NUMRVScores
    matched_apis: list[MatchedApi] = Field(default_factory=list)
    validation_score: float | None = None


class FeedbackRequest(BaseModel):
    hypothesis_id: str
    action: Literal["like", "dislike", "blacklist", "comment"]
    comment: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    last_batch_id: str | None = None
    last_run_at: datetime | None = None
    uptime_sec: float = Field(default=0.0)
