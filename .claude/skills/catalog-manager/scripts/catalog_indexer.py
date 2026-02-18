"""카탈로그 인덱서 — 전체/증분 임베딩 + FAISS 인덱스 생성 + 도메인 요약.

사용법:
    python catalog_indexer.py --full
    python catalog_indexer.py --incremental
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from config import (
    CATALOG_EMBEDDINGS_PATH,
    CATALOG_ID_MAP_PATH,
    CATALOG_INDEX_PATH,
)
from embedding_utils import EmbeddingService
from catalog_store import CatalogStore
from logger import get_logger

logger = get_logger("catalog_indexer")


def build_full_index(store: CatalogStore | None = None) -> int:
    """전체 카탈로그 임베딩 + FAISS 인덱스를 재생성한다.

    Returns:
        인덱싱된 API 수.
    """
    if store is None:
        store = CatalogStore()

    apis = store.list_apis(active_only=True)
    if not apis:
        logger.warning("No active APIs found — skipping index build")
        return 0

    # 임베딩용 텍스트: name + description + category
    texts = []
    id_map = []
    for api in apis:
        text = f"{api['name']} {api['description']} {api['category']}".strip()
        texts.append(text)
        id_map.append(api["api_id"])

    svc = EmbeddingService()
    svc.load_model()
    embeddings = svc.encode(texts)

    EmbeddingService.build_faiss_index(
        embeddings=embeddings,
        id_map=id_map,
        index_path=CATALOG_INDEX_PATH,
        id_map_path=CATALOG_ID_MAP_PATH,
        embeddings_path=CATALOG_EMBEDDINGS_PATH,
    )

    logger.info(f"Full index built: {len(apis)} APIs")
    return len(apis)


def build_incremental_index(store: CatalogStore | None = None) -> int:
    """신규/변경분만 임베딩을 재생성하고 인덱스에 추가한다.

    현재 단순 구현: 전체 재빌드. 향후 증분 최적화 예정.

    Returns:
        인덱싱된 API 수.
    """
    logger.info("Incremental index — falling back to full rebuild")
    return build_full_index(store)


def generate_domain_summaries(store: CatalogStore | None = None) -> int:
    """카테고리별 도메인 요약을 생성/갱신한다.

    Returns:
        갱신된 카테고리 수.
    """
    if store is None:
        store = CatalogStore()

    dist = store.get_category_distribution()
    count = 0
    for category, api_count in dist.items():
        apis = store.list_apis(category=category)
        # 대표 키워드: 상위 API 이름에서 추출
        names = [a["name"] for a in apis[:10]]
        keywords = ", ".join(names[:5])
        summary = f"{category} 분야 {api_count}개 API: {keywords}"
        store.upsert_domain_summary(category, api_count, keywords, summary)
        count += 1

    logger.info(f"Domain summaries updated: {count} categories")
    return count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="카탈로그 인덱서")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--full", action="store_true", help="전체 인덱스 재생성")
    group.add_argument("--incremental", action="store_true", help="증분 인덱스 갱신")
    args = parser.parse_args()

    store = CatalogStore()
    if args.full:
        build_full_index(store)
    else:
        build_incremental_index(store)
    generate_domain_summaries(store)
