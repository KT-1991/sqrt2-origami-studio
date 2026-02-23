from __future__ import annotations

from dataclasses import replace
import time
from typing import Dict, List, Optional, Sequence, Tuple

from creasegen.core_types import PointE
from creasegen.run_config import RunConfig
from creasegen.runtime_context import RunAppContext
from creasegen.stage_search_bindings import build_stage_search_config, build_stage_search_deps


def _draft_run_config(cfg: RunConfig) -> RunConfig:
    return replace(
        cfg,
        max_depth=max(0, min(cfg.max_depth, cfg.draft_max_depth)),
        branch_per_node=max(1, min(cfg.branch_per_node, cfg.draft_branch_per_node)),
        max_nodes=max(1, min(cfg.max_nodes, cfg.draft_max_nodes)),
        auto_expand_grid=False,
        final_prune=False,
        seed_auto_expand=False,
        render_image=False,
    )


def _extract_preferred_dir_hints(
    g,
    corner_ids: Sequence[int],
    cfg: RunConfig,
    *,
    ctx: RunAppContext,
) -> Dict[Tuple[int, int, int, int, int, int], List[int]]:
    hints: Dict[Tuple[int, int, int, int, int, int], List[int]] = {}
    tol = 1e-12
    for v in corner_ids:
        if v not in g.active_vertices:
            continue
        before_err = ctx.corner_condition_error(g, v, max_deg=cfg.corner_max_deg)
        need_lines = ctx.required_corner_lines(
            g,
            v,
            max_deg=cfg.corner_max_deg,
            min_corner_lines=cfg.min_corner_lines,
        )
        cur_lines = ctx.corner_line_count(g, v)
        deficit = max(0, need_lines - cur_lines)
        if deficit <= 0 and before_err <= tol:
            continue

        used = ctx.used_dir_indices(g, v, include_boundary=False)
        admissible = ctx.admissible_dirs_for_vertex(g, v, enforce_symmetry=cfg.enforce_symmetry)
        row = g.ensure_ray_next(v)
        cand: List[Tuple[float, int]] = []
        for d in admissible:
            if d in used:
                continue
            if row[d] is None:
                continue
            after_err = ctx.corner_condition_error_with_added_dir(g, v, d, max_deg=cfg.corner_max_deg)
            err_gain = before_err - after_err
            cand.append((err_gain, d))
        if not cand:
            continue
        cand.sort(key=lambda t: (-t[0], t[1]))
        need_dirs = min(len(cand), max(1, deficit))
        selected = [d for _, d in cand[:need_dirs]]
        if not selected:
            continue
        key = ctx.point_key(g.points[v])
        hints[key] = selected
    return hints


def _apply_preferred_hints_at_search_start(
    g,
    corner_ids: Sequence[int],
    preferred_dir_hints: Optional[Dict[Tuple[int, int, int, int, int, int], List[int]]],
    cfg: RunConfig,
    *,
    ctx: RunAppContext,
    stats: Dict[str, int],
) -> Tuple[object, Dict[str, int]]:
    if not preferred_dir_hints:
        return g, {
            "attempted": 0,
            "applied": 0,
            "failed": 0,
            "already_used": 0,
            "missing_corner": 0,
        }

    corner_key_to_vid: Dict[Tuple[int, int, int, int, int, int], int] = {}
    for v in corner_ids:
        if v not in g.active_vertices:
            continue
        corner_key_to_vid[ctx.point_key(g.points[v])] = v

    h = g
    attempted = 0
    applied = 0
    failed = 0
    already_used = 0
    missing_corner = 0

    for key, dirs in preferred_dir_hints.items():
        v = corner_key_to_vid.get(key)
        if v is None or v not in h.active_vertices:
            missing_corner += len(dirs)
            continue
        for d in dirs:
            attempted += 1
            if d in ctx.used_dir_indices(h, v, include_boundary=False):
                already_used += 1
                continue
            nh = ctx.apply_ray_action(
                h,
                v_idx=v,
                dir_idx=d,
                enforce_symmetry=cfg.enforce_symmetry,
                stats=stats,
            )
            if nh is None:
                failed += 1
                continue
            h = nh
            applied += 1

    return h, {
        "attempted": attempted,
        "applied": applied,
        "failed": failed,
        "already_used": already_used,
        "missing_corner": missing_corner,
    }


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
    preferred_dir_hints: Optional[Dict[Tuple[int, int, int, int, int, int], List[int]]] = None

    if cfg.draft_guided:
        draft_stats: Dict[str, int] = {}
        draft_seed = ctx.seed_expand_initial_graph(
            corners,
            make_grid_graph=ctx.make_grid_graph,
            merge_search_stats=ctx.merge_search_stats,
            expand_request_from_stats=ctx.expand_request_from_stats,
            **cfg.seed_expand_kwargs(),
            search_stats=draft_stats,
        )
        draft_deps = build_stage_search_deps(ctx)
        draft_cfg = _draft_run_config(cfg)
        draft_stage_config = build_stage_search_config(corners=corners, config=draft_cfg)
        draft_result = ctx.run_staged_search(
            draft_seed.graph,
            corner_ids=draft_seed.corner_ids,
            clone_graph=ctx.clone_graph,
            search_stage=ctx.search_stage,
            make_grid_graph=ctx.make_grid_graph,
            remap_graph_to_new_grid=ctx.remap_graph_to_new_grid,
            corner_score=ctx.corner_score,
            kawasaki_score=ctx.kawasaki_score,
            graph_stats=ctx.graph_stats,
            stage_deps=draft_deps,
            stage_config=draft_stage_config,
            search_stats=draft_stats,
            ks=draft_seed.k_start_effective,
            k_max=draft_cfg.k_max,
            budget=draft_seed.budget,
            preferred_dir_hints=None,
        )
        preferred_dir_hints = _extract_preferred_dir_hints(
            draft_result.graph,
            draft_result.corner_ids,
            cfg,
            ctx=ctx,
        )
        stage_logs.append(
            {
                "type": "draft_guided",
                "hint_corner_count": len(preferred_dir_hints),
                "hint_dir_total": sum(len(ds) for ds in preferred_dir_hints.values()),
                "draft_params": {
                    "max_depth": draft_cfg.max_depth,
                    "branch_per_node": draft_cfg.branch_per_node,
                    "max_nodes": draft_cfg.max_nodes,
                    "auto_expand_grid": draft_cfg.auto_expand_grid,
                    "seed_auto_expand": draft_cfg.seed_auto_expand,
                },
                "draft_seed_expand_rounds": draft_seed.seed_expand_rounds,
                "draft_stats_before": ctx.graph_stats(draft_seed.graph),
                "draft_stats_after": ctx.graph_stats(draft_result.graph),
            }
        )

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
    g, forced_hint_stats = _apply_preferred_hints_at_search_start(
        g,
        corner_ids,
        preferred_dir_hints,
        cfg,
        ctx=ctx,
        stats=search_stats,
    )
    if preferred_dir_hints:
        search_stats["draft_hint_forced_attempt"] = forced_hint_stats["attempted"]
        search_stats["draft_hint_forced_applied"] = forced_hint_stats["applied"]
        search_stats["draft_hint_forced_failed"] = forced_hint_stats["failed"]
        search_stats["draft_hint_forced_already_used"] = forced_hint_stats["already_used"]
        search_stats["draft_hint_forced_missing_corner"] = forced_hint_stats["missing_corner"]
        stage_logs.append(
            {
                "type": "draft_hint_force_start",
                "attempted": forced_hint_stats["attempted"],
                "applied": forced_hint_stats["applied"],
                "failed": forced_hint_stats["failed"],
                "already_used": forced_hint_stats["already_used"],
                "missing_corner": forced_hint_stats["missing_corner"],
                "stats_after": ctx.graph_stats(g),
            }
        )
    before_stats = ctx.graph_stats(g)
    before = ctx.corner_score(g, corner_ids=corner_ids, max_deg=cfg.corner_max_deg, min_corner_lines=cfg.min_corner_lines)
    before_k = ctx.kawasaki_score(g, tol=cfg.kawasaki_tol)
    before_ck = ctx.priority_corner_kawasaki_score(g, corner_ids=corner_ids, tol=cfg.kawasaki_tol)

    stage_deps = build_stage_search_deps(ctx)
    stage_config = build_stage_search_config(corners=corners, config=cfg)
    if preferred_dir_hints:
        search_stats["draft_hint_corner_count"] = len(preferred_dir_hints)
        search_stats["draft_hint_dir_total"] = sum(len(ds) for ds in preferred_dir_hints.values())
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
        preferred_dir_hints=preferred_dir_hints,
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
    params = cfg.result_params(
        a_work=work_budget.a_work,
        b_work=work_budget.b_work,
        a_norm_work=work_budget.a_norm_work,
        b_norm_work=work_budget.b_norm_work,
        effective_k=effective_k,
        seed_expand_rounds=seed_expand_rounds,
    )
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
    cp_graph_path: Optional[str] = None
    if cfg.cp_graph_path:
        cp_graph_payload = ctx.build_cp_graph_v1(
            best,
            corner_ids=corner_ids,
            params=params,
            search_stats=search_stats,
            stage_logs=stage_logs,
        )
        ctx.write_cp_graph_v1(cfg.cp_graph_path, cp_graph_payload)
        cp_graph_path = cfg.cp_graph_path
    elapsed = time.perf_counter() - t0
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
        cp_graph_path=cp_graph_path,
        render_image=cfg.render_image,
        out_path=cfg.out_path,
    )
