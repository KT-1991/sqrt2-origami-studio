from __future__ import annotations

from typing import Dict, Sequence, Tuple

from creasegen.stage_expand_planning import ExpandNeed, ExpandTarget


def apply_expand_target(
    best_local,
    need: ExpandNeed,
    target: ExpandTarget,
    *,
    corners: Sequence,
    make_grid_graph,
    remap_graph_to_new_grid,
    point_key,
    used_dir_indices,
    apply_ray_action,
    priority_corner_kawasaki_score,
    require_corner_kawasaki: bool,
    kawasaki_tol: float,
    enforce_symmetry: bool,
    use_local_ray_dirty: bool,
    search_stats: Dict[str, int],
):
    forced_corner_key = None
    if need.need_corner_v in best_local.active_vertices:
        forced_corner_key = point_key(best_local.points[need.need_corner_v])

    ng, ncorner_ids = make_grid_graph(
        corners,
        a_max=target.target_a,
        b_max=target.target_b,
        k_max=target.target_k,
        enforce_symmetry=enforce_symmetry,
        use_local_ray_dirty=use_local_ray_dirty,
    )
    remap_graph_to_new_grid(best_local, ng)

    if forced_corner_key is None or need.need_corner_d < 0:
        return ng, ncorner_ids

    search_stats["auto_expand_seed_attempt"] = search_stats.get("auto_expand_seed_attempt", 0) + 1
    forced_v = ng.point_to_id.get(forced_corner_key)
    if forced_v is None or forced_v not in ng.active_vertices:
        search_stats["auto_expand_seed_no_vertex"] = search_stats.get("auto_expand_seed_no_vertex", 0) + 1
        return ng, ncorner_ids

    if need.need_corner_d in used_dir_indices(ng, forced_v, include_boundary=False):
        search_stats["auto_expand_seed_used_dir"] = search_stats.get("auto_expand_seed_used_dir", 0) + 1
        return ng, ncorner_ids

    forced_h = apply_ray_action(
        ng,
        v_idx=forced_v,
        dir_idx=need.need_corner_d,
        enforce_symmetry=enforce_symmetry,
        stats=search_stats,
    )
    if forced_h is None:
        search_stats["auto_expand_seed_fail"] = search_stats.get("auto_expand_seed_fail", 0) + 1
        return ng, ncorner_ids

    if require_corner_kawasaki:
        ck_before = priority_corner_kawasaki_score(ng, corner_ids=ncorner_ids, tol=kawasaki_tol)
        ck_after = priority_corner_kawasaki_score(forced_h, corner_ids=ncorner_ids, tol=kawasaki_tol)
        if ck_after > ck_before:
            search_stats["auto_expand_seed_reject_corner_kawasaki"] = (
                search_stats.get("auto_expand_seed_reject_corner_kawasaki", 0) + 1
            )
            return ng, ncorner_ids

    search_stats["auto_expand_seed_success"] = search_stats.get("auto_expand_seed_success", 0) + 1
    return forced_h, ncorner_ids
