from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from creasegen.stage_expand_apply import apply_expand_target
from creasegen.stage_expand_planning import detect_expand_need, expand_mode, plan_expand_target
from creasegen.stage_search_policy import (
    can_trigger_auto_expand,
    evaluate_coarse_round,
    record_auto_expand_mode,
    record_auto_expand_trigger,
    record_coarse_round_improved,
    record_coarse_round_stalled,
    record_stage_iter_limit,
    update_stall_round_need_max,
)

__all__ = [
    "StageSearchDeps",
    "StageSearchConfig",
    "StageWorkBudget",
    "StageSearchResult",
    "search_stage",
]


@dataclass(frozen=True)
class StageSearchDeps:
    dfs_repair_corners: Any
    global_score: Any
    effective_stall_rounds: Any
    boundary_corner_promising_expand_targets: Any
    expand_request_from_stats: Any
    best_expand_move_for_corner: Any
    grid_required_corner_expand_request: Any
    make_grid_graph: Any
    remap_graph_to_new_grid: Any
    point_key: Any
    used_dir_indices: Any
    apply_ray_action: Any
    priority_corner_kawasaki_score: Any
    graph_stats: Any
    merge_search_stats: Any


@dataclass(frozen=True)
class StageSearchConfig:
    corners: Sequence
    corner_max_deg: float
    max_depth: int
    branch_per_node: int
    allow_violations: int
    max_nodes: int
    enforce_symmetry: bool
    enable_open_sink: bool
    enable_open_sink_repair: bool
    open_sink_max_bounces: int
    min_corner_lines: int
    kawasaki_tol: float
    enable_corner_kawasaki_repair: bool
    enable_triangle_macro: bool
    require_corner_kawasaki: bool
    dir_top_k: int
    priority_top_n: int
    stop_on_corner_clear: bool
    auto_expand_grid: bool
    auto_expand_max_rounds: int
    expand_stall_rounds: int
    staged_k_relax: bool
    use_local_ray_dirty: bool


@dataclass(frozen=True)
class StageWorkBudget:
    a_work: int
    b_work: int
    a_norm_work: int
    b_norm_work: int

    def enforce_k_floor(self, k_value: int) -> "StageWorkBudget":
        return StageWorkBudget(
            a_work=max(self.a_work, self.a_norm_work << k_value),
            b_work=max(self.b_work, self.b_norm_work << k_value),
            a_norm_work=self.a_norm_work,
            b_norm_work=self.b_norm_work,
        )


@dataclass(frozen=True)
class StageSearchResult:
    graph: object
    corner_ids: List[int]
    k: int
    budget: StageWorkBudget
    stage_logs: List[Dict[str, object]]


def search_stage(
    g_stage,
    corner_stage: List[int],
    stage_k: int,
    *,
    deps: StageSearchDeps,
    config: StageSearchConfig,
    budget: StageWorkBudget,
    search_stats: Dict[str, int],
    preferred_dir_hints: Optional[Dict[tuple, List[int]]] = None,
) -> StageSearchResult:
    d = deps
    cfg = config
    g_local = g_stage
    c_local = list(corner_stage)
    k_local = stage_k
    rounds = 0
    stall_streak = 0
    stage_logs: List[Dict[str, object]] = []
    work = budget

    def make_result(graph, corner_ids: List[int], k_value: int) -> StageSearchResult:
        return StageSearchResult(
            graph=graph,
            corner_ids=list(corner_ids),
            k=k_value,
            budget=work,
            stage_logs=stage_logs,
        )
    # Safety cap to avoid unbounded stage loops when running repeated coarse rounds.
    max_stage_iters = max(1, (cfg.auto_expand_max_rounds + 1) * 12)
    stage_iter = 0
    while True:
        stage_iter += 1
        if stage_iter > max_stage_iters:
            record_stage_iter_limit(search_stats)
            return make_result(g_local, c_local, k_local)
        base_sc = d.global_score(
            g_local,
            corner_ids=c_local,
            max_deg=cfg.corner_max_deg,
            min_corner_lines=cfg.min_corner_lines,
            kawasaki_tol=cfg.kawasaki_tol,
        )
        round_stats: Dict[str, int] = {}
        best_local = d.dfs_repair_corners(
            g_local,
            corner_ids=c_local,
            max_deg=cfg.corner_max_deg,
            max_depth=cfg.max_depth,
            branch_per_node=cfg.branch_per_node,
            allow_violations=cfg.allow_violations,
            max_nodes=cfg.max_nodes,
            enforce_symmetry=cfg.enforce_symmetry,
            enable_open_sink=cfg.enable_open_sink,
            enable_open_sink_repair=cfg.enable_open_sink_repair,
            open_sink_max_bounces=cfg.open_sink_max_bounces,
            min_corner_lines=cfg.min_corner_lines,
            kawasaki_tol=cfg.kawasaki_tol,
            enable_corner_kawasaki_repair=cfg.enable_corner_kawasaki_repair,
            enable_triangle_macro=cfg.enable_triangle_macro,
            require_corner_kawasaki=cfg.require_corner_kawasaki,
            search_stats=round_stats,
            dir_top_k=cfg.dir_top_k,
            priority_top_n=cfg.priority_top_n,
            stop_on_corner_clear=cfg.stop_on_corner_clear,
            preferred_dir_hints=preferred_dir_hints,
        )
        d.merge_search_stats(search_stats, round_stats)
        if not cfg.auto_expand_grid:
            return make_result(best_local, c_local, k_local)
        best_sc_local = d.global_score(
            best_local,
            corner_ids=c_local,
            max_deg=cfg.corner_max_deg,
            min_corner_lines=cfg.min_corner_lines,
            kawasaki_tol=cfg.kawasaki_tol,
        )
        round_status = evaluate_coarse_round(base_score=base_sc, best_score=best_sc_local)
        if round_status.improved:
            # Keep spending budget on coarse grid while improving.
            stall_streak = 0
            record_coarse_round_improved(search_stats)
            g_local = best_local
            if round_status.solved:
                return make_result(best_local, c_local, k_local)
            continue
        stall_streak += 1
        record_coarse_round_stalled(search_stats)
        g_local = best_local
        stall_need = d.effective_stall_rounds(
            active_vertices=len(g_local.active_vertices),
            base_rounds=cfg.expand_stall_rounds,
            max_nodes=cfg.max_nodes,
        )
        update_stall_round_need_max(search_stats, stall_need)
        if stall_streak < stall_need:
            continue

        need = detect_expand_need(
            best_local,
            corner_ids=c_local,
            round_stats=round_stats,
            boundary_corner_promising_expand_targets=d.boundary_corner_promising_expand_targets,
            expand_request_from_stats=d.expand_request_from_stats,
            best_expand_move_for_corner=d.best_expand_move_for_corner,
            grid_required_corner_expand_request=d.grid_required_corner_expand_request,
            corner_max_deg=cfg.corner_max_deg,
            min_corner_lines=cfg.min_corner_lines,
            enforce_symmetry=cfg.enforce_symmetry,
            search_stats=search_stats,
        )
        if need is None:
            return make_result(best_local, c_local, k_local)

        target = plan_expand_target(
            need,
            a_work=work.a_work,
            b_work=work.b_work,
            k_local=k_local,
            a_norm_work=work.a_norm_work,
            b_norm_work=work.b_norm_work,
            staged_k_relax=cfg.staged_k_relax,
        )
        if target is None:
            return make_result(best_local, c_local, k_local)
        if not can_trigger_auto_expand(
            rounds=rounds,
            auto_expand_max_rounds=cfg.auto_expand_max_rounds,
            stats=search_stats,
        ):
            return make_result(best_local, c_local, k_local)

        rounds += 1
        record_auto_expand_trigger(search_stats)
        mode = expand_mode(
            cur_a=work.a_work,
            cur_b=work.b_work,
            cur_k=k_local,
            cur_a_norm=work.a_norm_work,
            cur_b_norm=work.b_norm_work,
            target=target,
        )
        record_auto_expand_mode(search_stats, mode)

        work = StageWorkBudget(
            a_work=target.target_a,
            b_work=target.target_b,
            a_norm_work=target.target_a_norm,
            b_norm_work=target.target_b_norm,
        )
        ng, ncorner_ids = apply_expand_target(
            best_local,
            need,
            target,
            corners=cfg.corners,
            make_grid_graph=d.make_grid_graph,
            remap_graph_to_new_grid=d.remap_graph_to_new_grid,
            point_key=d.point_key,
            used_dir_indices=d.used_dir_indices,
            apply_ray_action=d.apply_ray_action,
            priority_corner_kawasaki_score=d.priority_corner_kawasaki_score,
            require_corner_kawasaki=cfg.require_corner_kawasaki,
            kawasaki_tol=cfg.kawasaki_tol,
            corner_max_deg=cfg.corner_max_deg,
            min_corner_lines=cfg.min_corner_lines,
            enforce_symmetry=cfg.enforce_symmetry,
            use_local_ray_dirty=cfg.use_local_ray_dirty,
            search_stats=search_stats,
        )
        g_local = ng
        c_local = ncorner_ids
        k_local = target.target_k
        stall_streak = 0
        stage_logs.append(
            {
                "type": "auto_expand",
                "reason": need.reason,
                "required_corner_count": need.need_count,
                "required_corner_v": need.need_corner_v,
                "required_corner_d": need.need_corner_d,
                "mode": mode,
                "a_max": work.a_work,
                "b_max": work.b_work,
                "a_norm": work.a_norm_work,
                "b_norm": work.b_norm_work,
                "k_max": k_local,
                "stats": d.graph_stats(g_local),
            }
        )
