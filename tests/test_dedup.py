"""MVP 게이트 테스트 — 중복 탐지 경계값 (0.84→미중복, 0.85→중복, 0.86→중복)."""

import sys
from pathlib import Path

import numpy as np
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SCORER_SCRIPTS = _PROJECT_ROOT / ".claude" / "skills" / "scorer" / "scripts"
if str(_SCORER_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCORER_SCRIPTS))

from dedup_engine import DedupEngine, _cosine_similarity


def _make_vectors_with_similarity(target_sim: float, dim: int = 128) -> tuple[np.ndarray, np.ndarray]:
    """지정된 코사인 유사도를 갖는 두 단위 벡터를 생성한다.

    theta = arccos(target_sim)
    vec_a = e1 (단위 벡터)
    vec_b = cos(theta)*e1 + sin(theta)*e2
    """
    theta = np.arccos(np.clip(target_sim, -1.0, 1.0))
    vec_a = np.zeros(dim)
    vec_a[0] = 1.0

    vec_b = np.zeros(dim)
    vec_b[0] = np.cos(theta)
    vec_b[1] = np.sin(theta)

    return vec_a, vec_b


class TestCosineSimlarity:
    """코사인 유사도 기본 테스트."""

    def test_identical_vectors(self):
        vec = np.array([1.0, 0.0, 0.0])
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert abs(_cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 0.0])
        assert _cosine_similarity(a, b) == 0.0


class TestDedupBoundary:
    """중복 탐지 경계값 — 0.84 → NOT duplicate, 0.85 → duplicate, 0.86 → duplicate."""

    def test_below_threshold_not_duplicate(self):
        """유사도 0.84 → 중복 아님."""
        vec_a, vec_b = _make_vectors_with_similarity(0.84)

        # 검증: 실제 유사도가 0.84에 근사한지
        actual_sim = _cosine_similarity(vec_a, vec_b)
        assert abs(actual_sim - 0.84) < 0.01

        engine = DedupEngine(threshold=0.85)
        ideas = [{"id": "I-01", "embedding": vec_a}]
        archive = np.array([vec_b])

        result = engine.check_duplicates(ideas, archive)
        assert result[0]["is_duplicate"] is False
        assert result[0]["max_similarity"] < 0.85

    def test_at_threshold_is_duplicate(self):
        """유사도 0.85 → 중복."""
        vec_a, vec_b = _make_vectors_with_similarity(0.85)

        actual_sim = _cosine_similarity(vec_a, vec_b)
        assert abs(actual_sim - 0.85) < 0.01

        engine = DedupEngine(threshold=0.85)
        ideas = [{"id": "I-01", "embedding": vec_a}]
        archive = np.array([vec_b])

        result = engine.check_duplicates(ideas, archive)
        assert result[0]["is_duplicate"] is True
        assert result[0]["max_similarity"] >= 0.85

    def test_above_threshold_is_duplicate(self):
        """유사도 0.86 → 중복."""
        vec_a, vec_b = _make_vectors_with_similarity(0.86)

        actual_sim = _cosine_similarity(vec_a, vec_b)
        assert abs(actual_sim - 0.86) < 0.01

        engine = DedupEngine(threshold=0.85)
        ideas = [{"id": "I-01", "embedding": vec_a}]
        archive = np.array([vec_b])

        result = engine.check_duplicates(ideas, archive)
        assert result[0]["is_duplicate"] is True
        assert result[0]["max_similarity"] >= 0.85


class TestDedupEdgeCases:
    """중복 탐지 엣지 케이스."""

    def test_no_archive(self):
        """아카이브 없음 → 모두 미중복."""
        engine = DedupEngine()
        ideas = [
            {"id": "I-01", "embedding": np.array([1.0, 0.0])},
            {"id": "I-02", "embedding": np.array([0.0, 1.0])},
        ]
        result = engine.check_duplicates(ideas, None)
        assert all(not idea["is_duplicate"] for idea in result)

    def test_empty_archive(self):
        """빈 아카이브 → 모두 미중복."""
        engine = DedupEngine()
        ideas = [{"id": "I-01", "embedding": np.array([1.0, 0.0])}]
        result = engine.check_duplicates(ideas, np.array([]))
        assert result[0]["is_duplicate"] is False

    def test_no_embedding(self):
        """임베딩 없는 아이디어 → 미중복."""
        engine = DedupEngine()
        ideas = [{"id": "I-01"}]  # no embedding
        archive = np.array([[1.0, 0.0]])
        result = engine.check_duplicates(ideas, archive)
        assert result[0]["is_duplicate"] is False

    def test_exact_duplicate(self):
        """완전 동일 벡터 → 유사도 1.0 → 중복."""
        engine = DedupEngine()
        vec = np.array([0.5, 0.5, 0.5])
        ideas = [{"id": "I-01", "embedding": vec}]
        archive = np.array([vec])

        result = engine.check_duplicates(ideas, archive)
        assert result[0]["is_duplicate"] is True
        assert abs(result[0]["max_similarity"] - 1.0) < 1e-4

    def test_multiple_archive_entries(self):
        """아카이브에 여러 항목 → 최대 유사도 기준 판정."""
        engine = DedupEngine(threshold=0.85)

        vec_a = np.array([1.0, 0.0, 0.0])
        arch_1 = np.array([0.0, 1.0, 0.0])  # orthogonal → sim ≈ 0
        arch_2 = np.array([0.9, 0.1, 0.0])  # close → sim high

        # normalize arch_2
        arch_2 = arch_2 / np.linalg.norm(arch_2)

        ideas = [{"id": "I-01", "embedding": vec_a}]
        archive = np.array([arch_1, arch_2])

        result = engine.check_duplicates(ideas, archive)
        # max_similarity는 arch_2와의 유사도 (높음)
        assert result[0]["max_similarity"] > 0.5

    def test_custom_threshold(self):
        """커스텀 임계값으로 호출."""
        engine = DedupEngine(threshold=0.85)
        vec_a, vec_b = _make_vectors_with_similarity(0.90)

        ideas = [{"id": "I-01", "embedding": vec_a}]
        archive = np.array([vec_b])

        # 기본 threshold(0.85)로 → 중복
        result = engine.check_duplicates(ideas, archive)
        assert result[0]["is_duplicate"] is True

        # 높은 threshold(0.95)로 → 미중복
        ideas2 = [{"id": "I-01", "embedding": vec_a}]
        result2 = engine.check_duplicates(ideas2, archive, threshold=0.95)
        assert result2[0]["is_duplicate"] is False
