"""MVP 게이트 테스트 — NUMR-V 가중 점수 + 등급 분류 (10-idea 배치)."""

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SCORER_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "scorer" / "scripts"
if str(_SCORER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCORER_SCRIPTS))

from numrv_scorer import NUMRVScorer
from grade_classifier import GradeClassifier


class TestNUMRVWeightedScore:
    """NUMR-V 가중 점수 산출 테스트."""

    def test_all_fives(self):
        """모든 차원 5점 → 가중합 = 5.0."""
        scorer = NUMRVScorer()
        scores = {"N": 5.0, "U": 5.0, "M": 5.0, "R": 5.0, "V": 5.0}
        result = scorer.calculate_weighted_score(scores)
        assert result == 5.0

    def test_all_zeros(self):
        """모든 차원 0점 → 가중합 = 0.0."""
        scorer = NUMRVScorer()
        scores = {"N": 0.0, "U": 0.0, "M": 0.0, "R": 0.0, "V": 0.0}
        result = scorer.calculate_weighted_score(scores)
        assert result == 0.0

    def test_weighted_calculation(self):
        """N=3, U=4, M=4, R=5, V=5 → 0.10*3 + 0.20*4 + 0.20*4 + 0.25*5 + 0.25*5 = 4.4."""
        scorer = NUMRVScorer()
        scores = {"N": 3.0, "U": 4.0, "M": 4.0, "R": 5.0, "V": 5.0}
        result = scorer.calculate_weighted_score(scores)
        expected = 0.10 * 3 + 0.20 * 4 + 0.20 * 4 + 0.25 * 5 + 0.25 * 5
        assert abs(result - expected) < 1e-6

    def test_rv_dominant(self):
        """R, V가 가장 큰 가중치(0.25) → R/V 높으면 N 낮아도 높은 점수."""
        scorer = NUMRVScorer()
        scores = {"N": 1.0, "U": 1.0, "M": 1.0, "R": 5.0, "V": 5.0}
        result = scorer.calculate_weighted_score(scores)
        # 0.1*1 + 0.2*1 + 0.2*1 + 0.25*5 + 0.25*5 = 0.1+0.2+0.2+1.25+1.25 = 3.0
        assert abs(result - 3.0) < 1e-6

    def test_only_novelty(self):
        """N만 5, 나머지 0 → 0.10*5 = 0.5."""
        scorer = NUMRVScorer()
        scores = {"N": 5.0, "U": 0.0, "M": 0.0, "R": 0.0, "V": 0.0}
        result = scorer.calculate_weighted_score(scores)
        assert abs(result - 0.5) < 1e-6

    def test_score_batch(self):
        """배치 점수 산출."""
        scorer = NUMRVScorer()
        ideas = [
            {"id": "I-1", "scores": {"N": 5, "U": 5, "M": 5, "R": 5, "V": 5}},
            {"id": "I-2", "scores": {"N": 0, "U": 0, "M": 0, "R": 0, "V": 0}},
        ]
        result = scorer.score_batch(ideas)
        assert result[0]["weighted_score"] == 5.0
        assert result[1]["weighted_score"] == 0.0


class TestGradeClassification:
    """등급 분류 테스트 — S(top10%+>=4.0), A(top30%+>=3.2), B(>=2.5), C(>=1.5), D(<1.5)."""

    def _make_10_ideas(self) -> list[dict]:
        """10개 아이디어 배치 생성 (점수 내림차순)."""
        return [
            {"id": f"I-{i+1:02d}", "weighted_score": score}
            for i, score in enumerate([
                4.8,  # rank 1 → top 10% (S)
                4.2,  # rank 2 → top 20% (A — top30% && >=3.2)
                3.8,  # rank 3 → top 30% (A — top30% && >=3.2)
                3.5,  # rank 4 → top 40% (B — >=2.5)
                3.0,  # rank 5 → top 50% (B)
                2.8,  # rank 6 → top 60% (B)
                2.5,  # rank 7 → top 70% (B — >=2.5)
                1.8,  # rank 8 → top 80% (C — >=1.5)
                1.5,  # rank 9 → top 90% (C — >=1.5)
                1.0,  # rank 10 → top 100% (D — <1.5)
            ])
        ]

    def test_10_idea_batch_grades(self):
        """10개 아이디어 배치에 대한 등급 분류."""
        classifier = GradeClassifier()
        ideas = self._make_10_ideas()
        result = classifier.classify(ideas)

        grades = {idea["id"]: idea["grade"] for idea in result}

        # S: top 10% (rank 1) AND score >= 4.0
        assert grades["I-01"] == "S", f"Expected S, got {grades['I-01']}"

        # A: top 30% (rank 2, 3) AND score >= 3.2
        assert grades["I-02"] == "A", f"Expected A, got {grades['I-02']}"
        assert grades["I-03"] == "A", f"Expected A, got {grades['I-03']}"

        # B: score >= 2.5
        assert grades["I-04"] == "B", f"Expected B, got {grades['I-04']}"
        assert grades["I-05"] == "B", f"Expected B, got {grades['I-05']}"
        assert grades["I-06"] == "B", f"Expected B, got {grades['I-06']}"
        assert grades["I-07"] == "B", f"Expected B, got {grades['I-07']}"

        # C: score >= 1.5
        assert grades["I-08"] == "C", f"Expected C, got {grades['I-08']}"
        assert grades["I-09"] == "C", f"Expected C, got {grades['I-09']}"

        # D: score < 1.5
        assert grades["I-10"] == "D", f"Expected D, got {grades['I-10']}"

    def test_s_requires_both_conditions(self):
        """S등급은 top 10% AND score >= 4.0 모두 만족해야 한다."""
        classifier = GradeClassifier()

        # 1등이지만 score < 4.0 → S 불가
        ideas = [
            {"id": "I-01", "weighted_score": 3.9},  # top 10% but <4.0
            {"id": "I-02", "weighted_score": 3.5},
            {"id": "I-03", "weighted_score": 3.0},
            {"id": "I-04", "weighted_score": 2.5},
            {"id": "I-05", "weighted_score": 2.0},
            {"id": "I-06", "weighted_score": 1.5},
            {"id": "I-07", "weighted_score": 1.0},
            {"id": "I-08", "weighted_score": 0.8},
            {"id": "I-09", "weighted_score": 0.5},
            {"id": "I-10", "weighted_score": 0.3},
        ]
        result = classifier.classify(ideas)
        # 1등이지만 3.9 < 4.0 이므로 S 아님 → A (top30% && >=3.2)
        assert result[0]["grade"] == "A"

    def test_a_requires_both_conditions(self):
        """A등급은 top 30% AND score >= 3.2 모두 만족해야 한다."""
        classifier = GradeClassifier()

        # top 20% 이지만 score < 3.2 → A 불가
        ideas = [
            {"id": "I-01", "weighted_score": 3.1},
            {"id": "I-02", "weighted_score": 3.0},
            {"id": "I-03", "weighted_score": 2.5},
            {"id": "I-04", "weighted_score": 2.0},
            {"id": "I-05", "weighted_score": 1.5},
        ]
        result = classifier.classify(ideas)
        # top 20% 이지만 3.1 < 3.2 → B (>=2.5)
        assert result[0]["grade"] == "B"

    def test_empty_list(self):
        classifier = GradeClassifier()
        result = classifier.classify([])
        assert result == []

    def test_single_idea_high(self):
        """단일 아이디어 score=4.5 → S (top 100/100 = 100% → 10% 이하? No → A)."""
        classifier = GradeClassifier()
        ideas = [{"id": "I-01", "weighted_score": 4.5}]
        result = classifier.classify(ideas)
        # rank=1, percentile=100% → top 10% 조건 불충족
        # 하지만 1/1 * 100 = 100% → percentile_rank=100% > 10% → S 불가
        # A 조건: 100% <= 30%? No → B (>=2.5? Yes)
        # 실제로 단일 아이디어는 1/1=100%이므로 S, A 모두 불가
        assert result[0]["grade"] == "B"

    def test_grade_distribution(self):
        """10개 배치 등급 분포 확인."""
        classifier = GradeClassifier()
        ideas = self._make_10_ideas()
        result = classifier.classify(ideas)

        dist = {}
        for idea in result:
            g = idea["grade"]
            dist[g] = dist.get(g, 0) + 1

        assert dist.get("S", 0) == 1
        assert dist.get("A", 0) == 2
        assert dist.get("B", 0) == 4
        assert dist.get("C", 0) == 2
        assert dist.get("D", 0) == 1
