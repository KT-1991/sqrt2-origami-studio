from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunAppContext:
    corners_diag_symmetric: Any
    seed_expand_initial_graph: Any
    merge_search_stats: Any
    expand_request_from_stats: Any
    make_grid_graph: Any
    graph_stats: Any
    corner_score: Any
    corner_condition_error: Any
    corner_line_count: Any
    required_corner_lines: Any
    corner_condition_error_with_added_dir: Any
    kawasaki_score: Any
    priority_corner_kawasaki_score: Any
    dfs_repair_corners: Any
    global_score: Any
    effective_stall_rounds: Any
    boundary_corner_promising_expand_targets: Any
    best_expand_move_for_corner: Any
    grid_required_corner_expand_request: Any
    remap_graph_to_new_grid: Any
    point_key: Any
    admissible_dirs_for_vertex: Any
    used_dir_indices: Any
    apply_ray_action: Any
    run_staged_search: Any
    clone_graph: Any
    search_stage: Any
    apply_final_prune_rounds: Any
    refresh_graph_by_pruning: Any
    preserve_satisfied_corners: Any
    collect_prune_axis_representatives: Any
    render_pattern: Any
    build_cp_graph_v1: Any
    write_cp_graph_v1: Any
    build_run_result: Any
    lattice_bounds_active: Any
    half: Any
