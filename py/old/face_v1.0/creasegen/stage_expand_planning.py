from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence


@dataclass(frozen=True)
class ExpandNeed:
    need_a: int
    need_b: int
    need_k: int
    need_a_norm: int
    need_b_norm: int
    need_count: int
    need_corner_v: int
    need_corner_d: int
    reason: str


@dataclass(frozen=True)
class ExpandTarget:
    target_a: int
    target_b: int
    target_k: int
    target_a_norm: int
    target_b_norm: int


def detect_expand_need(
    best_local,
    *,
    corner_ids: Sequence[int],
    round_stats: Dict[str, int],
    boundary_corner_promising_expand_targets,
    expand_request_from_stats,
    best_expand_move_for_corner,
    grid_required_corner_expand_request,
    corner_max_deg: float,
    min_corner_lines: int,
    enforce_symmetry: bool,
    search_stats: Dict[str, int],
) -> Optional[ExpandNeed]:
    promising_boundary = boundary_corner_promising_expand_targets(
        best_local,
        corner_ids=corner_ids,
        max_deg=corner_max_deg,
        min_corner_lines=min_corner_lines,
        enforce_symmetry=enforce_symmetry,
    )
    req_stats = expand_request_from_stats(round_stats)
    if req_stats is not None and promising_boundary:
        need_a, need_b, need_k, need_a_norm, need_b_norm = req_stats
        need_count = len(promising_boundary)
        need_corner_v = promising_boundary[0]
        need_corner_d = -1
        sel = best_expand_move_for_corner(
            best_local,
            v_idx=need_corner_v,
            enforce_symmetry=enforce_symmetry,
        )
        if sel is not None:
            need_corner_d = sel[0]
        search_stats["round_missing_grid_expand_detect"] = search_stats.get("round_missing_grid_expand_detect", 0) + 1
        search_stats["round_missing_grid_corner_count_max"] = max(
            search_stats.get("round_missing_grid_corner_count_max", 0),
            need_count,
        )
        return ExpandNeed(
            need_a=need_a,
            need_b=need_b,
            need_k=need_k,
            need_a_norm=need_a_norm,
            need_b_norm=need_b_norm,
            need_count=need_count,
            need_corner_v=need_corner_v,
            need_corner_d=need_corner_d,
            reason="round_missing_grid",
        )

    req = grid_required_corner_expand_request(
        best_local,
        corner_ids=corner_ids,
        max_deg=corner_max_deg,
        min_corner_lines=min_corner_lines,
        enforce_symmetry=enforce_symmetry,
    )
    if req is None:
        return None

    need_a, need_b, need_k, need_a_norm, need_b_norm, need_count, need_corner_v, need_corner_d = req
    search_stats["grid_required_corner_detect"] = search_stats.get("grid_required_corner_detect", 0) + 1
    search_stats["grid_required_corner_count_max"] = max(
        search_stats.get("grid_required_corner_count_max", 0),
        need_count,
    )
    return ExpandNeed(
        need_a=need_a,
        need_b=need_b,
        need_k=need_k,
        need_a_norm=need_a_norm,
        need_b_norm=need_b_norm,
        need_count=need_count,
        need_corner_v=need_corner_v,
        need_corner_d=need_corner_d,
        reason="grid_required_corner",
    )


def plan_expand_target(
    need: ExpandNeed,
    *,
    a_work: int,
    b_work: int,
    k_local: int,
    a_norm_work: int,
    b_norm_work: int,
    staged_k_relax: bool,
) -> Optional[ExpandTarget]:
    target_a = a_work
    target_b = b_work
    target_a_norm = a_norm_work
    target_b_norm = b_norm_work
    target_k = k_local if staged_k_relax else max(k_local, need.need_k)

    if need.reason == "round_missing_grid" and target_k > k_local:
        # Event-driven expansion: grow cautiously to avoid oversized jumps.
        target_k = min(target_k, k_local + 1)

    # Update a/b and a_norm/b_norm. Norm bounds tie coefficient budget to k.
    if need.reason == "round_missing_grid":
        target_a = max(a_work, min(need.need_a, a_work + 1))
        target_b = max(b_work, min(need.need_b, b_work + 1))
        target_a_norm = max(a_norm_work, min(need.need_a_norm, a_norm_work + 1))
        target_b_norm = max(b_norm_work, min(need.need_b_norm, b_norm_work + 1))
    else:
        target_a = max(a_work, need.need_a)
        target_b = max(b_work, need.need_b)
        target_a_norm = max(a_norm_work, need.need_a_norm)
        target_b_norm = max(b_norm_work, need.need_b_norm)

    # k-linked lower bounds from normalized coefficient budget.
    target_a = max(target_a, target_a_norm << target_k)
    target_b = max(target_b, target_b_norm << target_k)
    if (
        target_a <= a_work
        and target_b <= b_work
        and target_k <= k_local
        and target_a_norm <= a_norm_work
        and target_b_norm <= b_norm_work
    ):
        return None

    return ExpandTarget(
        target_a=target_a,
        target_b=target_b,
        target_k=target_k,
        target_a_norm=target_a_norm,
        target_b_norm=target_b_norm,
    )


def expand_mode(
    *,
    cur_a: int,
    cur_b: int,
    cur_k: int,
    cur_a_norm: int,
    cur_b_norm: int,
    target: ExpandTarget,
) -> str:
    k_changed = target.target_k > cur_k
    ab_changed = target.target_a > cur_a or target.target_b > cur_b
    norm_changed = target.target_a_norm > cur_a_norm or target.target_b_norm > cur_b_norm
    if k_changed and (not ab_changed) and (not norm_changed):
        return "k_only"
    return "with_ab"
