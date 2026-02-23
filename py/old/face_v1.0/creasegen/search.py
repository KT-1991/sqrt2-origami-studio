from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from creasegen.search_actions import apply_candidate_action
from creasegen.search_candidates import collect_trial_dirs, move_equivalence_key
from creasegen.search_policy import (
    child_sort_key,
    priority_corner_nonworse,
    prune_reason,
    refresh_acceptable,
    score_reject_reason,
    solved_by_score,
)


def dfs_repair_corners(
    g,
    corner_ids: Sequence[int],
    *,
    clone_graph,
    graph_state_key,
    global_score,
    priority_corner_kawasaki_score,
    refresh_graph_by_pruning,
    violating_vertex_priority,
    used_dir_indices,
    admissible_dirs_for_vertex,
    topk_dirs_for_vertex,
    mirrored_dir_idx,
    move_structure_tier,
    apply_open_sink_action,
    repair_priority_corners_open_sink,
    apply_ray_action,
    apply_triangle_macro_variants,
    max_deg: float = 45.0,
    max_depth: int = 24,
    branch_per_node: int = 14,
    allow_violations: int = 2,
    max_nodes: int = 4000,
    enforce_symmetry: bool = True,
    enable_open_sink: bool = True,
    enable_open_sink_repair: bool = True,
    open_sink_max_bounces: int = 14,
    min_corner_lines: int = 2,
    kawasaki_tol: float = 1e-8,
    enable_corner_kawasaki_repair: bool = True,
    enable_triangle_macro: bool = False,
    require_corner_kawasaki: bool = True,
    search_stats: Optional[Dict[str, int]] = None,
    refresh_every_nodes: int = 30,
    refresh_max_candidates: int = 24,
    dir_top_k: int = 4,
    priority_top_n: int = 6,
    stop_on_corner_clear: bool = False,
):
    stats = search_stats if search_stats is not None else {}

    def _inc(key: str, n: int = 1) -> None:
        stats[key] = stats.get(key, 0) + n

    score_cache: Dict[Tuple, Tuple[int, int, int, float, float, float]] = {}
    priority_cache: Dict[Tuple, Tuple[int, float]] = {}

    def _cached_global_score(state) -> Tuple[int, int, int, float, float, float]:
        sk = graph_state_key(state)
        cached = score_cache.get(sk)
        if cached is not None:
            return cached
        sc = global_score(
            state,
            corner_ids=corner_ids,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        score_cache[sk] = sc
        return sc

    def _cached_priority_corner_kawasaki(state) -> Tuple[int, float]:
        sk = graph_state_key(state)
        cached = priority_cache.get(sk)
        if cached is not None:
            return cached
        ck = priority_corner_kawasaki_score(state, corner_ids=corner_ids, tol=kawasaki_tol)
        priority_cache[sk] = ck
        return ck

    best = clone_graph(g)
    best_score = _cached_global_score(best)
    corner_set = set(corner_ids)
    seen: Set[Tuple] = {graph_state_key(g)}
    node_counter = 0
    solved = False

    def recurse(state, depth: int) -> None:
        nonlocal best, best_score, node_counter, solved
        _inc("recurse_calls")
        if solved:
            _inc("prune_already_solved")
            return
        node_counter += 1
        _inc("visited_nodes")
        if node_counter > max_nodes:
            _inc("prune_max_nodes")
            return
        sc = _cached_global_score(state)
        if sc < best_score:
            best = clone_graph(state)
            best_score = sc
        if stop_on_corner_clear and sc[1] == 0:
            solved = True
            _inc("stopped_corner_clear")
            best = clone_graph(state)
            best_score = sc
            return
        ck = _cached_priority_corner_kawasaki(state)
        if solved_by_score(sc, ck, require_corner_kawasaki=require_corner_kawasaki):
            solved = True
            _inc("solved_nodes")
            best = clone_graph(state)
            best_score = sc
            return
        p_reason = prune_reason(sc, depth=depth, max_depth=max_depth, allow_violations=allow_violations)
        if p_reason is not None:
            if p_reason == "max_depth":
                _inc("prune_max_depth")
            else:
                _inc("prune_allow_violations")
            return

        if refresh_every_nodes > 0 and depth > 0 and (node_counter % refresh_every_nodes == 0):
            _inc("refresh_trigger")
            refreshed, removed = refresh_graph_by_pruning(
                state,
                corner_ids=corner_ids,
                max_deg=max_deg,
                min_corner_lines=min_corner_lines,
                kawasaki_tol=kawasaki_tol,
                enforce_symmetry=enforce_symmetry,
                max_candidates=refresh_max_candidates,
            )
            if removed > 0:
                rkey = graph_state_key(refreshed)
                if rkey in seen:
                    _inc("refresh_reject_seen")
                else:
                    rsc = _cached_global_score(refreshed)
                    rck = _cached_priority_corner_kawasaki(refreshed)
                    if refresh_acceptable(
                        sc,
                        ck,
                        rsc,
                        rck,
                        require_corner_kawasaki=require_corner_kawasaki,
                    ):
                        seen.add(rkey)
                        state = refreshed
                        sc = rsc
                        ck = rck
                        _inc("refresh_applied")
                        _inc("refresh_removed_edges", removed)
                        if sc < best_score:
                            best = clone_graph(state)
                            best_score = sc
                    else:
                        _inc("refresh_reject_worse")
            else:
                _inc("refresh_nochange")

        priority = violating_vertex_priority(
            state,
            corner_ids=corner_ids,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        child_pool: List[Tuple[Tuple, object]] = []
        seen_move_equiv: Set[Tuple] = set()
        for v in priority[: max(1, priority_top_n)]:
            trial_pack = collect_trial_dirs(
                state,
                v_idx=v,
                used_dir_indices=used_dir_indices,
                admissible_dirs_for_vertex=admissible_dirs_for_vertex,
                topk_dirs_for_vertex=topk_dirs_for_vertex,
                dir_top_k=dir_top_k,
                enforce_symmetry=enforce_symmetry,
                stats_inc=_inc,
            )
            if trial_pack is None:
                continue
            trial_dirs, first_hit_map, mirror_v, mirror_row = trial_pack

            for d in trial_dirs:
                mk = move_equivalence_key(
                    v_idx=v,
                    dir_idx=d,
                    first_hit_map=first_hit_map,
                    enforce_symmetry=enforce_symmetry,
                    mirror_v=mirror_v,
                    mirror_row=mirror_row,
                    mirrored_dir_idx=mirrored_dir_idx,
                )
                if mk is None:
                    _inc("reject_no_first_hit")
                    continue
                if mk in seen_move_equiv:
                    _inc("reject_equiv_move")
                    continue
                seen_move_equiv.add(mk)
                move_tier = move_structure_tier(
                    state,
                    v_idx=v,
                    dir_idx=d,
                    corner_set=corner_set,
                    enforce_symmetry=enforce_symmetry,
                )
                h = apply_candidate_action(
                    state,
                    v_idx=v,
                    dir_idx=d,
                    enable_open_sink=enable_open_sink,
                    enable_open_sink_repair=enable_open_sink_repair,
                    enable_corner_kawasaki_repair=enable_corner_kawasaki_repair,
                    enforce_symmetry=enforce_symmetry,
                    open_sink_max_bounces=open_sink_max_bounces,
                    kawasaki_tol=kawasaki_tol,
                    corner_ids=corner_ids,
                    stats=stats,
                    apply_open_sink_action=apply_open_sink_action,
                    repair_priority_corners_open_sink=repair_priority_corners_open_sink,
                    apply_ray_action=apply_ray_action,
                )
                if h is None:
                    _inc("reject_action_failed")
                    continue
                k = graph_state_key(h)
                if k in seen:
                    _inc("reject_seen_state")
                    continue
                seen.add(k)
                hsc = _cached_global_score(h)
                reject_reason = score_reject_reason(sc, hsc, margin=2)
                if reject_reason == "kawasaki":
                    _inc("reject_score_bad_kawasaki")
                    continue
                if reject_reason == "corner":
                    _inc("reject_score_bad_corner")
                    continue
                if reject_reason == "lowline":
                    _inc("reject_score_bad_lowline")
                    continue
                if require_corner_kawasaki:
                    hck = _cached_priority_corner_kawasaki(h)
                    # Do not allow worsening on priority-corner Kawasaki violations.
                    if not priority_corner_nonworse(ck, hck):
                        _inc("reject_priority_corner_kawasaki")
                        continue
                child_key = child_sort_key(sc, hsc, move_tier)
                _inc("accepted_children")
                child_pool.append((child_key, h))
        child_pool.sort(key=lambda x: x[0])
        if len(child_pool) > branch_per_node:
            _inc("prune_branch_limit", len(child_pool) - branch_per_node)
        for _, h in child_pool[:branch_per_node]:
            recurse(h, depth + 1)

        if enable_triangle_macro and (not solved) and depth < max_depth:
            tri_children: List[Tuple[Tuple[int, int, int, float, float, float], object]] = []
            for v in priority[:3]:
                for h in apply_triangle_macro_variants(
                    state,
                    anchor_v=v,
                    enforce_symmetry=enforce_symmetry,
                    max_other_vertices=6,
                    max_centers=3,
                ):
                    k = graph_state_key(h)
                    if k in seen:
                        continue
                    seen.add(k)
                    hsc = _cached_global_score(h)
                    if require_corner_kawasaki:
                        hck = _cached_priority_corner_kawasaki(h)
                        if not priority_corner_nonworse(ck, hck):
                            continue
                    tri_children.append((hsc, h))
            tri_children.sort(key=lambda x: x[0])
            for _, h in tri_children[:max(1, branch_per_node // 2)]:
                recurse(h, depth + 1)

    recurse(g, 0)
    return best
