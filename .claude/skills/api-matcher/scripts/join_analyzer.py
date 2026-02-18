"""필드간 join 가능성 분석 — 공통 조인 키 탐지.

매칭된 API 쌍의 파라미터를 비교하여 시군구코드, 법정동코드 등 공통 키를 찾는다.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from logger import get_logger

logger = get_logger("join_analyzer")

# 알려진 공통 조인 키 패턴
KNOWN_JOIN_KEYS = [
    "시군구코드", "법정동코드", "행정동코드", "시도코드",
    "사업자번호", "사업자등록번호",
    "날짜", "기준일", "기준년월",
    "좌표", "위도", "경도", "위경도",
    "우편번호", "지번주소", "도로명주소",
]


class JoinAnalyzer:
    """API 쌍의 조인 가능성을 분석한다."""

    def __init__(self, known_keys: list[str] | None = None) -> None:
        self.known_keys = known_keys or KNOWN_JOIN_KEYS

    def find_join_keys(
        self,
        api_a_params: list[dict[str, str]],
        api_b_params: list[dict[str, str]],
    ) -> list[str]:
        """두 API의 파라미터 리스트에서 공통 조인 키를 찾는다.

        Args:
            api_a_params: [{"param_name": ..., "description": ...}, ...]
            api_b_params: 동일 형식

        Returns:
            공통 키 이름 리스트
        """
        a_names = {p.get("param_name", "").strip() for p in api_a_params}
        b_names = {p.get("param_name", "").strip() for p in api_b_params}

        # 정확히 같은 이름
        exact_matches = a_names & b_names

        # 알려진 키 포함 여부
        join_keys = set()
        all_names = a_names | b_names
        for key in self.known_keys:
            a_has = any(key in name for name in a_names)
            b_has = any(key in name for name in b_names)
            if a_has and b_has:
                join_keys.add(key)

        # 정확 매치도 추가
        join_keys.update(exact_matches - {""})

        return sorted(join_keys)

    def analyze_api_pairs(
        self,
        matched_apis: list[dict[str, Any]],
        get_params_fn: Any = None,
    ) -> list[dict[str, Any]]:
        """매칭된 API 리스트에서 모든 쌍의 조인 키를 분석한다.

        Args:
            matched_apis: [{"api_id": ..., "params": [...]}, ...]
            get_params_fn: api_id → params 조회 함수 (없으면 apis 내 params 사용)

        Returns:
            [{"api_pair": [id_a, id_b], "join_keys": [...]}, ...]
        """
        results = []
        for i, api_a in enumerate(matched_apis):
            for api_b in matched_apis[i + 1:]:
                params_a = api_a.get("params", [])
                params_b = api_b.get("params", [])

                if get_params_fn:
                    params_a = get_params_fn(api_a["api_id"])
                    params_b = get_params_fn(api_b["api_id"])

                keys = self.find_join_keys(params_a, params_b)
                if keys:
                    results.append({
                        "api_pair": [api_a["api_id"], api_b["api_id"]],
                        "join_keys": keys,
                    })

        logger.info(f"Analyzed {len(matched_apis)} APIs → {len(results)} joinable pairs")
        return results
