"""Stage 2 테스트 — 임베딩 서비스, FAISS 인덱스, 유사도 계산.

sentence-transformers/faiss가 없는 환경에서는 numpy 기반 목으로 테스트.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from embedding_utils import EmbeddingService


def _make_random_embeddings(n: int, dim: int = 128) -> np.ndarray:
    """정규화된 랜덤 임베딩을 생성한다."""
    vecs = np.random.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms


class TestEmbeddingServiceEncode:
    def test_encode_returns_ndarray(self):
        """모킹된 모델로 encode가 ndarray를 반환하는지 확인."""
        svc = EmbeddingService()
        mock_model = MagicMock()
        mock_model.encode.return_value = _make_random_embeddings(2)
        svc._model = mock_model

        result = svc.encode(["hello", "world"])
        assert isinstance(result, np.ndarray)
        assert result.shape[0] == 2


class TestFaissIndex:
    @pytest.fixture
    def index_files(self, tmp_path):
        """FAISS 인덱스를 빌드하고 파일 경로를 반환한다."""
        try:
            import faiss
        except ImportError:
            pytest.skip("faiss-cpu not installed")

        n, dim = 50, 128
        embeddings = _make_random_embeddings(n, dim)
        id_map = [f"API-{i:03d}" for i in range(n)]

        index_path = tmp_path / "test.faiss"
        id_map_path = tmp_path / "id_map.json"
        emb_path = tmp_path / "embeddings.npy"

        EmbeddingService.build_faiss_index(
            embeddings=embeddings,
            id_map=id_map,
            index_path=index_path,
            id_map_path=id_map_path,
            embeddings_path=emb_path,
        )

        return {
            "index_path": index_path,
            "id_map_path": id_map_path,
            "embeddings_path": emb_path,
            "embeddings": embeddings,
            "id_map": id_map,
            "dim": dim,
        }

    def test_build_creates_files(self, index_files):
        assert index_files["index_path"].exists()
        assert index_files["id_map_path"].exists()
        assert index_files["embeddings_path"].exists()

    def test_id_map_correct(self, index_files):
        with open(index_files["id_map_path"], "r") as f:
            loaded = json.load(f)
        assert len(loaded) == 50
        assert loaded[0] == "API-000"

    def test_search_returns_results(self, index_files):
        svc = EmbeddingService(
            index_path=index_files["index_path"],
            id_map_path=index_files["id_map_path"],
        )
        svc.load_index()

        # 모킹된 encode: 첫 번째 임베딩과 동일한 벡터를 반환
        query_vec = index_files["embeddings"][0:1]
        svc._model = MagicMock()
        svc._model.encode.return_value = query_vec

        results = svc.search("교통량", top_k=5)
        assert len(results) <= 5
        assert results[0]["api_id"] == "API-000"
        assert results[0]["score"] >= 0.99  # 자기 자신과의 유사도

    def test_search_ranks_correct(self, index_files):
        svc = EmbeddingService(
            index_path=index_files["index_path"],
            id_map_path=index_files["id_map_path"],
        )
        svc.load_index()

        query_vec = index_files["embeddings"][0:1]
        svc._model = MagicMock()
        svc._model.encode.return_value = query_vec

        results = svc.search("test", top_k=10)
        # 점수 내림차순 확인
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)


class TestCosineSimilarity:
    def test_identical_texts_high_similarity(self):
        svc = EmbeddingService()
        vec = _make_random_embeddings(1)
        svc._model = MagicMock()
        svc._model.encode.return_value = np.vstack([vec, vec])

        sim = svc.cosine_similarity("a", "a")
        assert sim > 0.99

    def test_batch_similarity(self):
        svc = EmbeddingService()
        n = 4
        vecs = _make_random_embeddings(n)
        svc._model = MagicMock()
        svc._model.encode.return_value = vecs

        results = svc.batch_cosine_similarity("query", ["a", "b", "c"])
        assert len(results) == 3
        assert all(isinstance(s, float) for s in results)


class TestIndexMissing:
    def test_load_index_file_not_found(self, tmp_path):
        try:
            import faiss
        except ImportError:
            pytest.skip("faiss-cpu not installed")

        svc = EmbeddingService(
            index_path=tmp_path / "missing.faiss",
            id_map_path=tmp_path / "missing.json",
        )
        with pytest.raises(FileNotFoundError):
            svc.load_index()
