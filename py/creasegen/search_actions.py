from __future__ import annotations

from typing import Dict, Optional, Sequence


def apply_candidate_action(
    state,
    *,
    v_idx: int,
    dir_idx: int,
    enable_open_sink: bool,
    enable_open_sink_repair: bool,
    enable_corner_kawasaki_repair: bool,
    enforce_symmetry: bool,
    open_sink_max_bounces: int,
    kawasaki_tol: float,
    corner_ids: Sequence[int],
    stats: Dict[str, int],
    apply_open_sink_action,
    repair_priority_corners_open_sink,
    apply_ray_action,
):
    if enable_open_sink:
        h = apply_open_sink_action(
            state,
            v_idx=v_idx,
            dir_idx=dir_idx,
            enforce_symmetry=enforce_symmetry,
            max_bounces=open_sink_max_bounces,
            enable_repair=enable_open_sink_repair,
            stats=stats,
        )
        if h is None:
            return None
        if enable_corner_kawasaki_repair:
            h = repair_priority_corners_open_sink(
                h,
                corner_ids=corner_ids,
                enforce_symmetry=enforce_symmetry,
                max_bounces=open_sink_max_bounces,
                tol=kawasaki_tol,
            )
        return h

    return apply_ray_action(
        state,
        v_idx=v_idx,
        dir_idx=dir_idx,
        enforce_symmetry=enforce_symmetry,
        stats=stats,
    )
