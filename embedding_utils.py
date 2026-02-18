"""임베딩 서비스 — 모델 로드, 쿼리 인코딩, top-K 검색, 유사도 계산.

sentence-transformers (ko-sroberta-multitask) + FAISS 인덱스.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from config import (
    CATALOG_EMBEDDINGS_PATH,
    CATALOG_ID_MAP_PATH,
    CATALOG_INDEX_PATH,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_TOP_K,
)
from logger import get_logger

logger = get_logger("embedding_utils")


class EmbeddingService:
    """임베딩 인코딩 + FAISS 인덱스 검색."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL_NAME,
        index_path: Path | str = CATALOG_INDEX_PATH,
        embeddings_path: Path | str = CATALOG_EMBEDDINGS_PATH,
        id_map_path: Path | str = CATALOG_ID_MAP_PATH,
    ) -> None:
        self.model_name = model_name
        self.index_path = Path(index_path)
        self.embeddings_path = Path(embeddings_path)
        self.id_map_path = Path(id_map_path)
        self._model = None
        self._index = None
        self._id_map: list[str] = []

    def load_model(self) -> None:
        """sentence-transformers 모델을 로드한다."""
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded: {self.model_name}")
        except ImportError:
            raise ImportError(
                "sentence-transformers가 설치되지 않았습니다. "
                "pip install sentence-transformers 를 실행하세요."
            )

    def load_index(self) -> None:
        """FAISS 인덱스 + ID 맵을 로드한다."""
        try:
            import faiss
        except ImportError:
            raise ImportError("faiss-cpu가 설치되지 않았습니다. pip install faiss-cpu 를 실행하세요.")

        if not self.index_path.exists():
            raise FileNotFoundError(f"FAISS 인덱스를 찾을 수 없습니다: {self.index_path}")
        if not self.id_map_path.exists():
            raise FileNotFoundError(f"ID 맵 파일을 찾을 수 없습니다: {self.id_map_path}")

        self._index = faiss.read_index(str(self.index_path))
        with open(self.id_map_path, "r", encoding="utf-8") as f:
            self._id_map = json.load(f)
        logger.info(f"FAISS index loaded: {self._index.ntotal} vectors")

    def encode(self, texts: list[str]) -> np.ndarray:
        """텍스트를 임베딩 벡터로 변환한다."""
        if self._model is None:
            self.load_model()
        return self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def search(self, query: str, top_k: int = EMBEDDING_TOP_K) -> list[dict[str, Any]]:
        """쿼리와 가장 유사한 top-K API를 반환한다.

        Returns:
            [{"api_id": ..., "score": float, "rank": int}, ...]
        """
        if self._index is None:
            self.load_index()

        query_vec = self.encode([query])
        distances, indices = self._index.search(query_vec.astype(np.float32), top_k)

        results = []
        for rank, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < 0 or idx >= len(self._id_map):
                continue
            results.append({
                "api_id": self._id_map[idx],
                "score": float(dist),
                "rank": rank + 1,
            })
        return results

    def cosine_similarity(self, text_a: str, text_b: str) -> float:
        """두 텍스트의 코사인 유사도를 반환한다."""
        vecs = self.encode([text_a, text_b])
        return float(np.dot(vecs[0], vecs[1]))

    def batch_cosine_similarity(self, query: str, candidates: list[str]) -> list[float]:
        """쿼리와 후보 리스트 각각의 코사인 유사도를 반환한다."""
        all_texts = [query] + candidates
        vecs = self.encode(all_texts)
        query_vec = vecs[0]
        return [float(np.dot(query_vec, vecs[i + 1])) for i in range(len(candidates))]

    @staticmethod
    def build_faiss_index(
        embeddings: np.ndarray,
        id_map: list[str],
        index_path: Path | str,
        id_map_path: Path | str,
        embeddings_path: Path | str | None = None,
    ) -> None:
        """FAISS 인덱스를 빌드하고 저장한다."""
        try:
            import faiss
        except ImportError:
            raise ImportError("faiss-cpu 필요")

        index_path = Path(index_path)
        id_map_path = Path(id_map_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)  # Inner Product (normalized → cosine)
        index.add(embeddings.astype(np.float32))
        faiss.write_index(index, str(index_path))

        with open(id_map_path, "w", encoding="utf-8") as f:
            json.dump(id_map, f, ensure_ascii=False)

        if embeddings_path:
            embeddings_path = Path(embeddings_path)
            embeddings_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(str(embeddings_path), embeddings)

        logger.info(f"FAISS index built: {index.ntotal} vectors, dim={dim}")
