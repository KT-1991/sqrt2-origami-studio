from __future__ import annotations

import time
from typing import Dict, List, Optional, Sequence, Tuple

from creasegen.core_types import PointE
from creasegen.run_config import RunConfig
from creasegen.runtime_context import RunAppContext
from creasegen.stage_search_bindings import build_stage_search_config, build_stage_search_deps


def run_app(
    corners: Sequence[PointE],
    config: RunConfig,
    *,
    ctx: RunAppContext,
) -> Dict[str, object]:
    cfg = config
    if cfg.enforce_symmetry and not ctx.corners_diag_symmetric(corners):
        raise ValueError("enforce_symmetry=True requires corners to be y=x symmetric")
    t0 = time.perf_counter()
    stage_logs: List[Dict[str, object]] = []
    search_stats: Dict[str, int] = {}
    seed_result = ctx.seed_expand_initial_graph(
        corners,
        make_grid_graph=ctx.make_grid_graph,
        merge_search_stats=ctx.merge_search_stats,
        expand_request_from_stats=ctx.expand_request_from_stats,
        **cfg.seed_expand_kwargs(),
        search_stats=search_stats,
    )
    g = seed_result.graph
    corner_ids = seed_result.corner_ids
    ks = seed_result.k_start_effective
    work_budget = seed_result.budget
    seed_expand_rounds = seed_result.seed_expand_rounds
    stage_logs.extend(seed_result.stage_logs)
    before_stats = ctx.graph_stats(g)
    before = ctx.corner_score(g, corner_ids=corner_ids, max_deg=cfg.corner_max_deg, min_corner_lines=cfg.min_corner_lines)
    before_k = ctx.kawasaki_score(g, tol=cfg.kawasaki_tol)
    before_ck = ctx.priority_corner_kawasaki_score(g, corner_ids=corner_ids, tol=cfg.kawasaki_tol)

    stage_deps = build_stage_search_deps(ctx)
    stage_config = build_stage_search_config(corners=corners, config=cfg)
    staged_result = ctx.run_staged_search(
        g,
        corner_ids=corner_ids,
        clone_graph=ctx.clone_graph,
        search_stage=ctx.search_stage,
        make_grid_graph=ctx.make_grid_graph,
        remap_graph_to_new_grid=ctx.remap_graph_to_new_grid,
        corner_score=ctx.corner_score,
        kawasaki_score=ctx.kawasaki_score,
        graph_stats=ctx.graph_stats,
        stage_deps=stage_deps,
        stage_config=stage_config,
        search_stats=search_stats,
        ks=ks,
        k_max=cfg.k_max,
        budget=work_budget,
    )
    best = staged_result.graph
    corner_ids = staged_result.corner_ids
    effective_k = staged_result.effective_k
    work_budget = staged_result.budget
    stage_logs.extend(staged_result.stage_logs)

    if cfg.final_prune and cfg.final_prune_rounds > 0 and cfg.final_prune_max_candidates > 0:
        best, prune_logs = ctx.apply_final_prune_rounds(
            best,
            corner_ids=corner_ids,
            refresh_graph_by_pruning=ctx.refresh_graph_by_pruning,
            global_score=ctx.global_score,
            priority_corner_kawasaki_score=ctx.priority_corner_kawasaki_score,
            corner_score=ctx.corner_score,
            preserve_satisfied_corners=ctx.preserve_satisfied_corners,
            graph_stats=ctx.graph_stats,
            **cfg.final_prune_kwargs(),
            half=ctx.half,
            search_stats=search_stats,
        )
        stage_logs.extend(prune_logs)

    after = ctx.corner_score(best, corner_ids=corner_ids, max_deg=cfg.corner_max_deg, min_corner_lines=cfg.min_corner_lines)
    after_k = ctx.kawasaki_score(best, tol=cfg.kawasaki_tol)
    after_ck = ctx.priority_corner_kawasaki_score(best, corner_ids=corner_ids, tol=cfg.kawasaki_tol)
    corner_errs = [ctx.corner_condition_error(best, v, max_deg=cfg.corner_max_deg) for v in corner_ids]
    corner_line_counts = [ctx.corner_line_count(best, v) for v in corner_ids]
    prune_axes: Optional[List[Tuple[int, int, int]]] = None
    if cfg.show_prune_axes and cfg.prune_axes_max > 0:
        reps = ctx.collect_prune_axis_representatives(best, max_candidates=cfg.prune_axes_max)
        prune_axes = [(e[0], e[1], clen) for e, clen in reps]
    if cfg.render_image:
        ctx.render_pattern(
            best,
            corner_ids=corner_ids,
            out_path=cfg.out_path,
            show_order=cfg.show_order,
            highlight_kawasaki=cfg.highlight_kawasaki,
            kawasaki_tol=cfg.kawasaki_tol,
            prune_axes=prune_axes,
        )
    elapsed = time.perf_counter() - t0
    params = cfg.result_params(
        a_work=work_budget.a_work,
        b_work=work_budget.b_work,
        a_norm_work=work_budget.a_norm_work,
        b_norm_work=work_budget.b_norm_work,
        effective_k=effective_k,
        seed_expand_rounds=seed_expand_rounds,
    )
    return ctx.build_run_result(
        elapsed_sec=elapsed,
        params=params,
        before_stats=before_stats,
        graph_stats_after=ctx.graph_stats(best),
        lattice_bounds_after=ctx.lattice_bounds_active(best),
        corner_score_before=before,
        corner_score_after=after,
        kawasaki_score_before=before_k,
        kawasaki_score_after=after_k,
        priority_corner_kawasaki_before=before_ck,
        priority_corner_kawasaki_after=after_ck,
        corner_errors_after=corner_errs,
        corner_line_counts_after=corner_line_counts,
        min_corner_lines=cfg.min_corner_lines,
        prune_axes_count=(len(prune_axes) if prune_axes is not None else 0),
        half=ctx.half,
        search_stats=search_stats,
        stage_logs=stage_logs,
        staged_k_relax=cfg.staged_k_relax,
        auto_expand_grid=cfg.auto_expand_grid,
        render_image=cfg.render_image,
        out_path=cfg.out_path,
    )
