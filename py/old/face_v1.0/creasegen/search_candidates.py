from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple


def collect_trial_dirs(
    state,
    v_idx: int,
    *,
    used_dir_indices,
    admissible_dirs_for_vertex,
    topk_dirs_for_vertex,
    dir_top_k: int,
    enforce_symmetry: bool,
    stats_inc: Callable[[str, int], None],
) -> Optional[Tuple[List[int], Dict[int, Optional[int]], Optional[int], Optional[List[Optional[int]]]]]:
    used = used_dir_indices(state, v_idx, include_boundary=False)
    feasible_dirs: List[int] = []
    first_hit_map: Dict[int, Optional[int]] = {}
    row_v = state.ensure_ray_next(v_idx)
    for d in admissible_dirs_for_vertex(state, v_idx, enforce_symmetry=enforce_symmetry):
        stats_inc("candidate_dirs_total", 1)
        if d in used:
            stats_inc("reject_used_dir", 1)
            continue
        hit_v = row_v[d]
        if hit_v is None:
            stats_inc("reject_no_ray_hit", 1)
            continue
        feasible_dirs.append(d)
        first_hit_map[d] = hit_v
    if not feasible_dirs:
        return None

    trial_dirs = topk_dirs_for_vertex(
        state,
        v_idx=v_idx,
        dirs=feasible_dirs,
        used_dirs=used,
        k=dir_top_k,
        first_hit_map=first_hit_map,
    )
    if len(trial_dirs) < len(feasible_dirs):
        stats_inc("reject_topk_drop", len(feasible_dirs) - len(trial_dirs))

    mirror_v: Optional[int] = None
    mirror_row: Optional[List[Optional[int]]] = None
    if enforce_symmetry:
        mirror_v = state.mirror_vertex_idx(v_idx)
        if mirror_v is not None:
            mirror_row = state.ensure_ray_next(mirror_v)
    return trial_dirs, first_hit_map, mirror_v, mirror_row


def move_equivalence_key(
    *,
    v_idx: int,
    dir_idx: int,
    first_hit_map: Dict[int, Optional[int]],
    enforce_symmetry: bool,
    mirror_v: Optional[int],
    mirror_row: Optional[List[Optional[int]]],
    mirrored_dir_idx,
) -> Optional[Tuple]:
    first_hit = first_hit_map.get(dir_idx)
    if first_hit is None:
        return None

    first_key: Tuple = ("V", first_hit)
    mirror_key: Optional[Tuple] = None
    if enforce_symmetry:
        if mirror_v is None:
            mirror_key = ("MISSING_MIRROR_VERTEX",)
        else:
            md = mirrored_dir_idx(dir_idx)
            mhit = mirror_row[md] if mirror_row is not None else None
            mirror_key = None if mhit is None else ("V", mhit)
    return (v_idx, first_key, mirror_key)
