from __future__ import annotations

from typing import Dict, Optional, Tuple

from creasegen.core_types import _ceil_div_pow2


def _required_norm_bounds_from_grid_bounds(a_max: int, b_max: int, k: int) -> Tuple[int, int]:
    return (_ceil_div_pow2(max(0, a_max), max(0, k)), _ceil_div_pow2(max(0, b_max), max(0, k)))


def _merge_search_stats(dst: Dict[str, int], src: Dict[str, int]) -> None:
    for k, v in src.items():
        if k.startswith("expand_need_"):
            dst[k] = max(dst.get(k, 0), v)
        else:
            dst[k] = dst.get(k, 0) + v


def _expand_request_from_stats(stats: Dict[str, int]) -> Optional[Tuple[int, int, int, int, int]]:
    ra = stats.get("expand_need_a_max", 0)
    rb = stats.get("expand_need_b_max", 0)
    rk = stats.get("expand_need_k_max", 0)
    ran = stats.get("expand_need_a_norm", 0)
    rbn = stats.get("expand_need_b_norm", 0)
    if ra <= 0 and rb <= 0 and rk <= 0 and ran <= 0 and rbn <= 0:
        return None
    if ("expand_need_a_norm" not in stats) or ("expand_need_b_norm" not in stats):
        raise ValueError(
            "expand stats missing normalized bounds: expand_need_a_norm and expand_need_b_norm are required"
        )
    if ran < 0 or rbn < 0:
        raise ValueError("expand stats normalized bounds must be non-negative")
    return (ra, rb, rk, ran, rbn)


def _effective_stall_rounds(active_vertices: int, base_rounds: int, max_nodes: int) -> int:
    # Aim for roughly one coarse sweep before expanding.
    # Each coarse round is bounded by max_nodes, so use that as coverage proxy.
    cover = max(1, max_nodes)
    approx = (max(0, active_vertices) + cover - 1) // cover
    return max(1, base_rounds, min(12, approx))
