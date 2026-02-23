from __future__ import annotations

from functools import partial
from math import pi
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from creasegen.core_types import (
    ANGLE_COUNT,
    DIRS_F,
    HALF,
    ONE,
    PointE,
    Qsqrt2,
    ZERO,
)
from creasegen.scoring import (
    _interior_wedge,
    _norm_angle,
    corner_condition_error,
    corner_line_count,
    corner_score,
    incident_angles,
    required_corner_lines,
    unique_angles,
)
from creasegen.parsing import corners_diag_symmetric
from creasegen.expand import (
    _effective_stall_rounds,
    _expand_request_from_stats,
    _merge_search_stats,
    _required_norm_bounds_from_grid_bounds,
)
from creasegen.direction import (
    _angle_of_dir_idx,
    _dir_gap_steps,
    _in_ccw_interval,
    _nearest_dir_idx,
    _reflected_dir_idx,
    _symmetric_candidate_dirs,
)
from creasegen.predicates import (
    _is_boundary_vertex,
    _is_square_corner_vertex,
    _on_diag_vertex,
    diagonal_symmetry_ok,
)
from creasegen.geometry import (
    _crosses_existing_edges,
    _is_point_on_line,
)
from creasegen.grid_utils import (
    _point_k_level,
    _point_key,
    _required_grid_bounds_for_point,
    mirrored_dir_idx,
)
from creasegen.actions import (
    apply_open_sink_action as _apply_open_sink_action_impl,
    apply_ray_action as _apply_ray_action_impl,
    deactivate_isolated_noncorner_vertices as _deactivate_isolated_noncorner_vertices_impl,
    repair_open_sink_vertices as _repair_open_sink_vertices_impl,
    repair_priority_corners_open_sink as _repair_priority_corners_open_sink_impl,
    run_delete_group_transaction as _run_delete_group_transaction_impl,
    run_open_sink_transaction as _run_open_sink_transaction_impl,
)
from creasegen.prune_axes import (
    best_axis_cycle_group_for_line as _best_axis_cycle_group_for_line_impl,
    collect_axis_cycle_targets as _collect_axis_cycle_targets_impl,
    collect_prune_axis_representatives as _collect_prune_axis_representatives_impl,
    edge_center_dist2 as _edge_center_dist2_impl,
    edge_line_key as _edge_line_key_impl,
    line_key_eq as _line_key_eq_impl,
    refresh_graph_by_pruning as _refresh_graph_by_pruning_impl,
)
from creasegen.seeding import (
    boundary_corner_promising_expand_targets as _boundary_corner_promising_expand_targets_impl,
    corner_condition_error_with_added_dir as _corner_condition_error_with_added_dir_impl,
    exact_dir_idx_from_delta as _exact_dir_idx_from_delta_impl,
    is_aligned_with_16_dirs as _is_aligned_with_16_dirs_impl,
    seed_direct_corner_connections as _seed_direct_corner_connections_impl,
    used_dir_indices as _used_dir_indices_impl,
)
from creasegen.triangle import (
    add_segment_with_splits_ids as _add_segment_with_splits_ids_impl,
    apply_triangle_macro_variants as _apply_triangle_macro_variants_impl,
)
from creasegen.evaluation import (
    global_score as _global_score_impl,
    kawasaki_score as _kawasaki_score_impl,
    preserve_satisfied_corners as _preserve_satisfied_corners_impl,
    priority_corner_kawasaki_score as _priority_corner_kawasaki_score_impl,
    violating_vertex_priority as _violating_vertex_priority_impl,
)
from creasegen.search import dfs_repair_corners as _dfs_repair_corners_impl
from creasegen.auto_expand import (
    best_expand_move_for_corner as _best_expand_move_for_corner_impl,
    grid_required_corner_expand_request as _grid_required_corner_expand_request_impl,
    move_growth_probe as _move_growth_probe_impl,
    single_ray_growth_probe as _single_ray_growth_probe_impl,
)
from creasegen.graph_ops import (
    adopt_graph_state as _adopt_graph_state_impl,
    clone_graph as _clone_graph_impl,
    graph_state_key as _graph_state_key_impl,
    graph_stats as _graph_stats_impl,
    lattice_bounds_active as _lattice_bounds_active_impl,
    make_grid_graph as _make_grid_graph_impl,
    remap_graph_to_new_grid as _remap_graph_to_new_grid_impl,
)
from creasegen.final_prune import apply_final_prune_rounds as _apply_final_prune_rounds_impl
from creasegen.stage_search import search_stage as _search_stage_impl
from creasegen.pipeline_search import (
    run_staged_search as _run_staged_search_impl,
    seed_expand_initial_graph as _seed_expand_initial_graph_impl,
)
from creasegen.cp_graph_v1 import (
    build_cp_graph_v1 as _build_cp_graph_v1_impl,
    write_cp_graph_v1 as _write_cp_graph_v1_impl,
)
from creasegen.result_payload import build_run_result as _build_run_result_impl
from creasegen.rendering import render_pattern as _render_pattern_impl
from creasegen.graph import GridCreaseGraph, enumerate_grid_points





def adopt_graph_state(dst: GridCreaseGraph, src: GridCreaseGraph) -> None:
    _adopt_graph_state_impl(dst, src)


def find_vertex_idx(g: GridCreaseGraph, p: PointE) -> Optional[int]:
    return g.point_to_id.get(_point_key(p))


def admissible_dirs_for_vertex(g: GridCreaseGraph, v_idx: int, enforce_symmetry: bool) -> List[int]:
    dirs = list(range(ANGLE_COUNT))
    px, py = g.points_f[v_idx]
    start, width = _interior_wedge(px, py, eps=1e-10)
    if width < 2 * pi - 1e-10:
        end = start + width
        dirs = [d for d in dirs if _in_ccw_interval(_angle_of_dir_idx(d), start, end)]

    if enforce_symmetry and _on_diag_vertex(g, v_idx):
        out: List[int] = []
        seen: Set[Tuple[int, int]] = set()
        for d in dirs:
            md = mirrored_dir_idx(d)
            pair = (d, md) if d <= md else (md, d)
            if pair in seen:
                continue
            seen.add(pair)
            if d == md:
                continue
            out.append(min(d, md))
        dirs = out
    return dirs


def _incident_dir_indices(g: GridCreaseGraph, v_idx: int) -> List[int]:
    if v_idx not in g.incident_dirs_dirty:
        cached = g.incident_dirs_cache.get(v_idx)
        if cached is not None:
            return cached
    # Hot path: use float-direction quantization instead of exact Qsqrt2 delta math.
    # Edges are constrained to 16 directions, so nearest-bin mapping is stable in practice.
    vx, vy = g.points_f[v_idx]
    out: Set[int] = set()
    for u in g.adj.get(v_idx, set()):
        ux, uy = g.points_f[u]
        out.add(_nearest_dir_idx(ux - vx, uy - vy))
    result = sorted(out)
    g.incident_dirs_cache[v_idx] = result
    g.incident_dirs_dirty.discard(v_idx)
    return result


def _sector_steps_cyclic(sorted_dirs: Sequence[int]) -> List[int]:
    if not sorted_dirs:
        return []
    out: List[int] = []
    n = len(sorted_dirs)
    for i in range(n):
        a = sorted_dirs[i]
        b = sorted_dirs[(i + 1) % n]
        out.append((b - a) % ANGLE_COUNT)
    return out


def _kawasaki_residual_from_dirs(sorted_dirs: Sequence[int]) -> float:
    n = len(sorted_dirs)
    if n % 2 != 0 or n == 0:
        return float("inf")
    # Allow straight-through vertices: 2 incident directions that are opposite.
    if n == 2:
        d = abs(sorted_dirs[1] - sorted_dirs[0]) % ANGLE_COUNT
        d = min(d, ANGLE_COUNT - d)
        return 0.0 if d == (ANGLE_COUNT // 2) else float("inf")
    if n < 4:
        return float("inf")
    sec_steps = _sector_steps_cyclic(sorted_dirs)
    target = ANGLE_COUNT // 2
    odd_steps = sum(sec_steps[::2])
    even_steps = sum(sec_steps[1::2])
    return float(abs(odd_steps - target) + abs(even_steps - target)) * (pi / 8.0)


def vertex_kawasaki_error(g: GridCreaseGraph, v_idx: int) -> float:
    if v_idx not in g.kawasaki_dirty:
        cached = g.kawasaki_cache.get(v_idx)
        if cached is not None:
            return cached
    ke = _kawasaki_residual_from_dirs(_incident_dir_indices(g, v_idx))
    g.kawasaki_cache[v_idx] = ke
    g.kawasaki_dirty.discard(v_idx)
    return ke


def _kawasaki_target_vertex_ids(g: GridCreaseGraph) -> List[int]:
    return [v for v in sorted(g.active_vertices) if not _is_boundary_vertex(g, v)]












def _single_ray_growth_class(g: GridCreaseGraph, origin_v: int, dir_idx: int) -> int:
    # 0: no new vertex, 1: new vertex on current grid, 2: needs finer grid
    hit = g.ray_hit_at(origin_v, dir_idx)
    if hit is None:
        return 2
    _, _, hit_pos, p = hit
    if hit_pos != 0:
        return 0
    hit_v = g.point_to_id.get(_point_key(p))
    if hit_v is None:
        return 2
    if hit_v in g.active_vertices:
        return 0
    return 1


def _move_structure_tier(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
    corner_set: Set[int],
    enforce_symmetry: bool,
) -> int:
    # Requested priority tiers:
    # 0: non-corner, no vertex increase
    # 1: non-corner, vertex increase within current grid
    # 2: corner
    # 3: non-corner, vertex increase that would require finer grid
    if v_idx in corner_set:
        return 2
    grow = _single_ray_growth_class(g, v_idx, dir_idx)
    if enforce_symmetry:
        mv = g.mirror_vertex_idx(v_idx)
        if mv is None:
            return 3
        md = mirrored_dir_idx(dir_idx)
        grow = max(grow, _single_ray_growth_class(g, mv, md))
    if grow <= 0:
        return 0
    if grow == 1:
        return 1
    return 3


def _topk_dirs_for_vertex(
    g: GridCreaseGraph,
    v_idx: int,
    dirs: Sequence[int],
    used_dirs: Set[int],
    k: int,
    first_hit_map: Optional[Dict[int, Optional[int]]] = None,
) -> List[int]:
    if k <= 0 or len(dirs) <= k:
        return list(dirs)
    used_sorted = sorted(used_dirs)
    scored: List[Tuple[float, int, int, int]] = []
    for d in dirs:
        local = sorted(set(used_dirs | {d}))
        ke = _kawasaki_residual_from_dirs(local)
        if first_hit_map is None:
            hit_v = g.ray_next_at(v_idx, d)
        else:
            hit_v = first_hit_map.get(d)
        bpen = 1 if (hit_v is not None and _is_boundary_vertex(g, hit_v)) else 0
        if used_sorted:
            gap = min(_dir_gap_steps(d, ud) for ud in used_sorted)
        else:
            gap = 0
        scored.append((ke, bpen, gap, d))
    scored.sort()
    return [d for _, _, _, d in scored[:k]]


def _edge_dir_from(g: GridCreaseGraph, v_idx: int, u_idx: int) -> Optional[int]:
    e = g._norm_edge(v_idx, u_idx)
    b = g.edge_dir_idx.get(e)
    if b is not None:
        vx, vy = g.points_f[v_idx]
        ux, uy = g.points_f[u_idx]
        dx = ux - vx
        dy = uy - vy
        bx, by = DIRS_F[b]
        if dx * bx + dy * by >= 0.0:
            return b
        return (b + ANGLE_COUNT // 2) % ANGLE_COUNT

    vp = g.points[v_idx]
    up = g.points[u_idx]
    d = _exact_dir_idx_from_delta(up.x - vp.x, up.y - vp.y)
    if d is not None:
        return d
    vx, vy = g.points_f[v_idx]
    ux, uy = g.points_f[u_idx]
    return _nearest_dir_idx(ux - vx, uy - vy)


def _deactivate_isolated_noncorner_vertices(g: GridCreaseGraph, corner_ids: Sequence[int]) -> None:
    _deactivate_isolated_noncorner_vertices_impl(g, corner_ids)


def _finite_kawasaki_error(g: GridCreaseGraph, v: int) -> float:
    ke = vertex_kawasaki_error(g, v)
    return 1000.0 if ke == float("inf") else ke


def _local_kawasaki_metric(
    g: GridCreaseGraph,
    verts: Iterable[int],
    tol: float,
) -> Tuple[int, float]:
    bad = 0
    total = 0.0
    for v in verts:
        if v not in g.active_vertices:
            continue
        if _is_boundary_vertex(g, v):
            continue
        ke = _finite_kawasaki_error(g, v)
        if ke > tol:
            bad += 1
        total += ke
    return bad, total


def _cross(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2) -> Qsqrt2:
    return ax * by - ay * bx


























def seed_direct_corner_connections(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    max_deg: float = 45.0,
    min_corner_lines: int = 2,
    enforce_symmetry: bool = True,
    stats: Optional[Dict[str, int]] = None,
) -> None:
    _seed_direct_corner_connections_impl(
        g,
        corner_ids=corner_ids,
        is_aligned_with_16_dirs_fn=_is_aligned_with_16_dirs,
        is_square_corner_vertex=_is_square_corner_vertex,
        priority_corner_kawasaki_score=priority_corner_kawasaki_score,
        kawasaki_score=kawasaki_score,
        corner_condition_error=corner_condition_error,
        corner_line_count=corner_line_count,
        required_corner_lines_fn=required_corner_lines,
        is_boundary_vertex=_is_boundary_vertex,
        clone_graph=clone_graph,
        add_segment_with_splits_ids=_add_segment_with_splits_ids,
        diagonal_symmetry_ok=diagonal_symmetry_ok,
        adopt_graph_state=adopt_graph_state,
        max_deg=max_deg,
        min_corner_lines=min_corner_lines,
        enforce_symmetry=enforce_symmetry,
        stats=stats,
    )


def corner_condition_error_with_added_dir(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
    max_deg: float,
) -> float:
    return _corner_condition_error_with_added_dir(
        g,
        v_idx,
        dir_idx,
        max_deg=max_deg,
    )


























def remap_graph_to_new_grid(src: GridCreaseGraph, dst: GridCreaseGraph) -> None:
    _remap_graph_to_new_grid_impl(src, dst, point_key=_point_key)




def render_pattern(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    out_path: str = "_tmp_out/grid_pattern.png",
    show_order: bool = False,
    highlight_kawasaki: bool = False,
    kawasaki_tol: float = 1e-8,
    prune_axes: Optional[Sequence[Tuple[int, int, int]]] = None,
) -> None:
    _render_pattern_impl(
        g,
        corner_ids=corner_ids,
        out_path=out_path,
        show_order=show_order,
        highlight_kawasaki=highlight_kawasaki,
        kawasaki_tol=kawasaki_tol,
        prune_axes=prune_axes,
        kawasaki_target_vertex_ids=_kawasaki_target_vertex_ids,
        vertex_kawasaki_error=vertex_kawasaki_error,
    )










# Thin forwarding aliases (avoid repetitive wrapper bodies).
clone_graph = partial(_clone_graph_impl, graph_cls=GridCreaseGraph)
_line_key_eq = _line_key_eq_impl
_edge_center_dist2 = _edge_center_dist2_impl
_exact_dir_idx_from_delta = _exact_dir_idx_from_delta_impl
_is_aligned_with_16_dirs = _is_aligned_with_16_dirs_impl
used_dir_indices = partial(_used_dir_indices_impl, edge_dir_from=_edge_dir_from)
_corner_condition_error_with_added_dir = partial(
    _corner_condition_error_with_added_dir_impl,
    interior_wedge=_interior_wedge,
    norm_angle=_norm_angle,
    incident_angles=incident_angles,
    unique_angles=unique_angles,
    angle_of_dir_idx=_angle_of_dir_idx,
)
_boundary_corner_promising_expand_targets = partial(
    _boundary_corner_promising_expand_targets_impl,
    is_boundary_vertex=_is_boundary_vertex,
    corner_condition_error=corner_condition_error,
    corner_line_count=corner_line_count,
    required_corner_lines_fn=required_corner_lines,
    used_dir_indices_fn=used_dir_indices,
    admissible_dirs_for_vertex=admissible_dirs_for_vertex,
    corner_condition_error_with_added_dir_fn=_corner_condition_error_with_added_dir,
    topk_dirs_for_vertex=_topk_dirs_for_vertex,
)
kawasaki_score = partial(
    _kawasaki_score_impl,
    kawasaki_target_vertex_ids=_kawasaki_target_vertex_ids,
    vertex_kawasaki_error=vertex_kawasaki_error,
)
global_score = partial(
    _global_score_impl,
    corner_score_fn=corner_score,
    kawasaki_score_fn=kawasaki_score,
)
priority_corner_kawasaki_score = partial(
    _priority_corner_kawasaki_score_impl,
    is_boundary_vertex=_is_boundary_vertex,
    vertex_kawasaki_error=vertex_kawasaki_error,
)
violating_vertex_priority = partial(
    _violating_vertex_priority_impl,
    corner_condition_error=corner_condition_error,
    corner_line_count=corner_line_count,
    kawasaki_target_vertex_ids=_kawasaki_target_vertex_ids,
    vertex_kawasaki_error=vertex_kawasaki_error,
    is_boundary_vertex=_is_boundary_vertex,
)
graph_state_key = _graph_state_key_impl

apply_ray_action = partial(
    _apply_ray_action_impl,
    clone_graph=clone_graph,
    mirrored_dir_idx=mirrored_dir_idx,
    diagonal_symmetry_ok=diagonal_symmetry_ok,
)
_run_open_sink_transaction = partial(
    _run_open_sink_transaction_impl,
    incident_dir_indices=_incident_dir_indices,
    admissible_dirs_for_vertex=admissible_dirs_for_vertex,
    symmetric_candidate_dirs=_symmetric_candidate_dirs,
    kawasaki_residual_from_dirs=_kawasaki_residual_from_dirs,
    find_vertex_idx=find_vertex_idx,
    on_diag_vertex=_on_diag_vertex,
    is_boundary_vertex=_is_boundary_vertex,
    reflected_dir_idx=_reflected_dir_idx,
    diagonal_symmetry_ok=diagonal_symmetry_ok,
)

def _repair_open_sink_vertices_dispatch(*args, **kwargs):
    return _repair_open_sink_vertices(*args, **kwargs)

apply_open_sink_action = partial(
    _apply_open_sink_action_impl,
    clone_graph=clone_graph,
    mirrored_dir_idx=mirrored_dir_idx,
    run_open_sink_transaction=_run_open_sink_transaction,
    repair_open_sink_vertices=_repair_open_sink_vertices_dispatch,
    diagonal_symmetry_ok=diagonal_symmetry_ok,
)
_repair_open_sink_vertices = partial(
    _repair_open_sink_vertices_impl,
    kawasaki_target_vertex_ids=_kawasaki_target_vertex_ids,
    vertex_kawasaki_error=vertex_kawasaki_error,
    incident_dir_indices=_incident_dir_indices,
    admissible_dirs_for_vertex=admissible_dirs_for_vertex,
    symmetric_candidate_dirs=_symmetric_candidate_dirs,
    kawasaki_residual_from_dirs=_kawasaki_residual_from_dirs,
    apply_open_sink_action=apply_open_sink_action,
)
_repair_priority_corners_open_sink = partial(
    _repair_priority_corners_open_sink_impl,
    is_boundary_vertex=_is_boundary_vertex,
    vertex_kawasaki_error=vertex_kawasaki_error,
    incident_dir_indices=_incident_dir_indices,
    admissible_dirs_for_vertex=admissible_dirs_for_vertex,
    kawasaki_residual_from_dirs=_kawasaki_residual_from_dirs,
    apply_open_sink_action=apply_open_sink_action,
)

_edge_line_key = partial(_edge_line_key_impl, edge_dir_from=_edge_dir_from, cross=_cross)
_run_delete_group_transaction = partial(
    _run_delete_group_transaction_impl,
    kawasaki_score=kawasaki_score,
    local_kawasaki_metric=_local_kawasaki_metric,
    clone_graph=clone_graph,
    deactivate_isolated_noncorner_vertices=_deactivate_isolated_noncorner_vertices,
    diagonal_symmetry_ok=diagonal_symmetry_ok,
)
_best_axis_cycle_group_for_line = _best_axis_cycle_group_for_line_impl
_collect_prune_axis_representatives = partial(
    _collect_prune_axis_representatives_impl,
    edge_line_key_fn=_edge_line_key,
    edge_center_dist2_fn=_edge_center_dist2,
    best_axis_cycle_group_for_line_fn=_best_axis_cycle_group_for_line,
)
_collect_axis_cycle_targets = partial(
    _collect_axis_cycle_targets_impl,
    edge_line_key_fn=_edge_line_key,
    edge_center_dist2_fn=_edge_center_dist2,
    best_axis_cycle_group_for_line_fn=_best_axis_cycle_group_for_line,
)
_refresh_graph_by_pruning = partial(
    _refresh_graph_by_pruning_impl,
    clone_graph=clone_graph,
    global_score=global_score,
    priority_corner_kawasaki_score=priority_corner_kawasaki_score,
    edge_line_key_fn=_edge_line_key,
    collect_axis_cycle_targets_fn=_collect_axis_cycle_targets,
    line_key_eq_fn=_line_key_eq,
    run_delete_group_transaction_fn=_run_delete_group_transaction,
)

_add_segment_with_splits_ids = partial(
    _add_segment_with_splits_ids_impl,
    exact_dir_idx_from_delta=_exact_dir_idx_from_delta,
    crosses_existing_edges=_crosses_existing_edges,
    is_point_on_line=_is_point_on_line,
)
apply_triangle_macro_variants = partial(
    _apply_triangle_macro_variants_impl,
    add_segment_with_splits_ids_fn=_add_segment_with_splits_ids,
    clone_graph=clone_graph,
    diagonal_symmetry_ok=diagonal_symmetry_ok,
    graph_state_key=graph_state_key,
    exact_dir_idx_from_delta=_exact_dir_idx_from_delta,
)

_preserve_satisfied_corners = partial(
    _preserve_satisfied_corners_impl,
    corner_condition_error=corner_condition_error,
    corner_line_count=corner_line_count,
)
dfs_repair_corners = partial(
    _dfs_repair_corners_impl,
    clone_graph=clone_graph,
    graph_state_key=graph_state_key,
    global_score=global_score,
    priority_corner_kawasaki_score=priority_corner_kawasaki_score,
    refresh_graph_by_pruning=_refresh_graph_by_pruning,
    violating_vertex_priority=violating_vertex_priority,
    used_dir_indices=used_dir_indices,
    admissible_dirs_for_vertex=admissible_dirs_for_vertex,
    topk_dirs_for_vertex=_topk_dirs_for_vertex,
    mirrored_dir_idx=mirrored_dir_idx,
    move_structure_tier=_move_structure_tier,
    apply_open_sink_action=apply_open_sink_action,
    repair_priority_corners_open_sink=_repair_priority_corners_open_sink,
    apply_ray_action=apply_ray_action,
    apply_triangle_macro_variants=apply_triangle_macro_variants,
    point_key=_point_key,
)
make_grid_graph = partial(
    _make_grid_graph_impl,
    enumerate_grid_points=enumerate_grid_points,
    graph_cls=GridCreaseGraph,
    seed_direct_corner_connections=seed_direct_corner_connections,
    add_segment_with_splits_ids=_add_segment_with_splits_ids,
    point_cls=PointE,
    zero=ZERO,
    one=ONE,
)
graph_stats = partial(_graph_stats_impl, point_k_level=_point_k_level)
lattice_bounds_active = _lattice_bounds_active_impl

_single_ray_growth_probe = partial(
    _single_ray_growth_probe_impl,
    point_key=_point_key,
    required_grid_bounds_for_point=_required_grid_bounds_for_point,
)
_move_growth_probe = partial(
    _move_growth_probe_impl,
    single_ray_growth_probe_fn=_single_ray_growth_probe,
    mirrored_dir_idx=mirrored_dir_idx,
)
_best_expand_move_for_corner = partial(
    _best_expand_move_for_corner_impl,
    used_dir_indices_fn=used_dir_indices,
    admissible_dirs_for_vertex=admissible_dirs_for_vertex,
    move_growth_probe_fn=_move_growth_probe,
    required_norm_bounds_from_grid_bounds=_required_norm_bounds_from_grid_bounds,
)
_grid_required_corner_expand_request = partial(
    _grid_required_corner_expand_request_impl,
    corner_condition_error=corner_condition_error,
    corner_line_count=corner_line_count,
    required_corner_lines_fn=required_corner_lines,
    used_dir_indices_fn=used_dir_indices,
    admissible_dirs_for_vertex=admissible_dirs_for_vertex,
    move_growth_probe_fn=_move_growth_probe,
    required_norm_bounds_from_grid_bounds=_required_norm_bounds_from_grid_bounds,
)


# RunAppContext bindings (single place for runtime pipeline wiring)
seed_expand_initial_graph = _seed_expand_initial_graph_impl
merge_search_stats = _merge_search_stats
expand_request_from_stats = _expand_request_from_stats
effective_stall_rounds = _effective_stall_rounds
boundary_corner_promising_expand_targets = _boundary_corner_promising_expand_targets
best_expand_move_for_corner = _best_expand_move_for_corner
grid_required_corner_expand_request = _grid_required_corner_expand_request
point_key = _point_key
run_staged_search = _run_staged_search_impl
search_stage = _search_stage_impl
apply_final_prune_rounds = _apply_final_prune_rounds_impl
refresh_graph_by_pruning = _refresh_graph_by_pruning
preserve_satisfied_corners = _preserve_satisfied_corners
collect_prune_axis_representatives = _collect_prune_axis_representatives
build_cp_graph_v1 = _build_cp_graph_v1_impl
write_cp_graph_v1 = _write_cp_graph_v1_impl
build_run_result = _build_run_result_impl
half = HALF
