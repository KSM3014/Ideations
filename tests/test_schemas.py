"""MVP 게이트 테스트 #2 — Pydantic 모델 직렬화/역직렬화."""

from datetime import datetime, timezone, timedelta

import pytest

from server.schemas.api_contracts import (
    SCHEMA_VERSION,
    ApiSuggestion,
    BatchSummary,
    CompetitorInfo,
    DataNeed,
    FeedbackRequest,
    HealthResponse,
    Hypothesis,
    HypothesisMatch,
    HypothesisValidation,
    IdeaDetail,
    JoinKey,
    MatchedApi,
    NUMRVScores,
    Phase1Output,
    Phase2Output,
    Phase3Output,
    Phase4Output,
    Phase5Output,
    Phase6Output,
    PipelineResult,
    PublishResult,
    ScoredIdea,
    SignalItem,
    ValidationScores,
)

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 2, 18, 14, 0, 0, tzinfo=KST)


class TestSchemaVersion:
    def test_all_base_schemas_have_version(self):
        p1 = Phase1Output(batch_id="test", signals=[], sources_attempted=[], sources_succeeded=[])
        assert p1.schema_version == SCHEMA_VERSION

        p2 = Phase2Output(batch_id="test")
        assert p2.schema_version == SCHEMA_VERSION


class TestPhase1:
    def test_signal_item_roundtrip(self):
        item = SignalItem(
            source="google_trends",
            title="AI 헬스케어",
            url="https://example.com",
            snippet="요약",
            collected_at=NOW,
        )
        data = item.model_dump()
        restored = SignalItem.model_validate(data)
        assert restored.source == "google_trends"
        assert restored.title == "AI 헬스케어"

    def test_phase1_output_serialization(self):
        output = Phase1Output(
            batch_id="20260218-1400-abc12345",
            signals=[
                SignalItem(source="news", title="정책 변경", collected_at=NOW),
            ],
            sources_attempted=["google_trends", "news"],
            sources_succeeded=["news"],
            duration_sec=120.5,
        )
        j = output.model_dump_json()
        restored = Phase1Output.model_validate_json(j)
        assert len(restored.signals) == 1
        assert restored.duration_sec == 120.5


class TestPhase2:
    def test_hypothesis_full_fields(self):
        h = Hypothesis(
            id="H-001",
            service_name="공공 교통 알리미",
            problem="실시간 교통 정보 부족",
            solution="공공 API 기반 실시간 교통 대시보드",
            target_buyer="지자체 교통과",
            revenue_model="SaaS 구독",
            data_needs=[DataNeed(field_name="교통량", description="시간대별 교통량")],
            api_suggestions=[ApiSuggestion(api_name="교통량 API", reason="실시간 교통량 제공")],
        )
        data = h.model_dump()
        assert data["id"] == "H-001"
        assert len(data["data_needs"]) == 1

    def test_phase2_output_roundtrip(self):
        output = Phase2Output(
            batch_id="test",
            hypotheses=[
                Hypothesis(
                    id="H-001",
                    service_name="서비스A",
                    problem="문제",
                    solution="솔루션",
                    target_buyer="타깃",
                    revenue_model="모델",
                )
            ],
            retry_count=1,
            duration_sec=300.0,
        )
        j = output.model_dump_json()
        restored = Phase2Output.model_validate_json(j)
        assert len(restored.hypotheses) == 1
        assert restored.retry_count == 1


class TestPhase3:
    def test_hypothesis_match(self):
        match = HypothesisMatch(
            hypothesis_id="H-001",
            matched_apis=[
                MatchedApi(api_id="API-100", api_name="교통량 API", relevance_score=0.82, matched_fields=["교통량"]),
            ],
            join_keys=[JoinKey(key_name="시군구코드", api_pair=["API-100", "API-200"])],
            missing_data=["주차장"],
            feasibility_pct=65.0,
            passed=True,
        )
        assert match.passed is True
        assert match.feasibility_pct == 65.0

    def test_feasibility_boundary_40(self):
        """적합도 경계값: 39% → 탈락, 40% → 통과."""
        fail = HypothesisMatch(hypothesis_id="H-F", matched_apis=[], missing_data=[], feasibility_pct=39.0, passed=False)
        pass_ = HypothesisMatch(hypothesis_id="H-P", matched_apis=[], missing_data=[], feasibility_pct=40.0, passed=True)
        assert not fail.passed
        assert pass_.passed


class TestPhase4:
    def test_validation_scores_total(self):
        scores = ValidationScores(
            competitor_analysis=20,
            market_demand_proxy=15,
            timing_fit=12,
            revenue_reference=10,
            mvp_difficulty=8,
        )
        assert scores.total == 65

    def test_score_constraints(self):
        with pytest.raises(Exception):
            ValidationScores(
                competitor_analysis=30,  # max 25
                market_demand_proxy=0,
                timing_fit=0,
                revenue_reference=0,
                mvp_difficulty=0,
            )


class TestPhase5:
    def test_numrv_scores(self):
        scores = NUMRVScores(N=4.0, U=3.5, M=4.0, R=3.0, V=4.5)
        data = scores.model_dump()
        assert all(1 <= v <= 5 for v in data.values())

    def test_scored_idea_grades(self):
        for grade in ("S", "A", "B", "C", "D"):
            idea = ScoredIdea(
                hypothesis_id="H-001",
                service_name="서비스",
                numrv=NUMRVScores(N=3, U=3, M=3, R=3, V=3),
                weighted_score=3.0,
                grade=grade,
            )
            assert idea.grade == grade


class TestPhase6:
    def test_publish_result_defaults(self):
        result = PublishResult()
        assert not result.dashboard_updated
        assert not result.discord_sent
        assert result.archive_appended == 0


class TestPipelineResult:
    def test_full_pipeline_serialization(self):
        pipeline = PipelineResult(
            batch_id="20260218-1400-abc12345",
            started_at=NOW,
            finished_at=NOW,
            total_duration_sec=3500.0,
            success=True,
        )
        j = pipeline.model_dump_json()
        restored = PipelineResult.model_validate_json(j)
        assert restored.success is True
        assert restored.batch_id == "20260218-1400-abc12345"


class TestApiServer:
    def test_feedback_request_actions(self):
        for action in ("like", "dislike", "blacklist", "comment"):
            fb = FeedbackRequest(hypothesis_id="H-001", action=action)
            assert fb.action == action

    def test_health_response(self):
        health = HealthResponse(status="ok", uptime_sec=3600.0)
        assert health.status == "ok"
