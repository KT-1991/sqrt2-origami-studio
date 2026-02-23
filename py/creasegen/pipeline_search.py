from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from creasegen.stage_search import StageSearchConfig, StageSearchDeps, StageSearchResult, StageWorkBudget

__all__ = [
    "SeedExpandResult",
    "StagedSearchResult",
    "seed_expand_initial_graph",
    "run_staged_search",
]


@dataclass(frozen=True)
class StagedSearchResult:
    graph: object
    corner_ids: List[int]
    effective_k: int
    budget: StageWorkBudget
    stage_logs: List[Dict[str, object]]


@dataclass(frozen=True)
class SeedExpandResult:
    graph: object
    corner_ids: List[int]
    k_start_effective: int
    budget: StageWorkBudget
    seed_expand_rounds: int
    stage_logs: List[Dict[str, object]]


def seed_expand_initial_graph(
    corners: Sequence,
    *,
    make_grid_graph,
    merge_search_stats,
    expand_request_from_stats,
    staged_k_relax: bool,
    k_start: int,
    k_max: int,
    a_max: int,
    b_max: int,
    corner_max_deg: float,
    min_corner_lines: int,
    seed_auto_expand: bool,
    seed_auto_expand_max_rounds: int,
    enforce_symmetry: bool,
    use_local_ray_dirty: bool,
    search_stats: Dict[str, int],
) -> SeedExpandResult:
    if staged_k_relax:
        ks = max(1, min(k_start, k_max))
    else:
        ks = k_max

    work = StageWorkBudget(
        a_work=a_max,
        b_work=b_max,
        a_norm_work=0,
        b_norm_work=0,
    )
    stage_logs: List[Dict[str, object]] = []

    seed_expand_rounds = 0
    while True:
        seed_stats: Dict[str, int] = {}
        g, corner_ids = make_grid_graph(
            corners,
            a_max=work.a_work,
            b_max=work.b_work,
            k_max=ks,
            corner_max_deg=corner_max_deg,
            min_corner_lines=min_corner_lines,
            enforce_symmetry=enforce_symmetry,
            use_local_ray_dirty=use_local_ray_dirty,
            seed_stats=seed_stats,
        )
        merge_search_stats(search_stats, seed_stats)
        if not seed_auto_expand:
            break
        req_seed = expand_request_from_stats(seed_stats)
        if req_seed is None:
            break
        if seed_expand_rounds >= max(0, seed_auto_expand_max_rounds):
            search_stats["seed_auto_expand_round_limit"] = search_stats.get("seed_auto_expand_round_limit", 0) + 1
            break
        need_a, need_b, need_k, need_a_norm, need_b_norm = req_seed
        target_k = ks if staged_k_relax else max(ks, need_k)
        target_a_norm = max(work.a_norm_work, need_a_norm)
        target_b_norm = max(work.b_norm_work, need_b_norm)
        target_a = max(work.a_work, need_a, target_a_norm << target_k)
        target_b = max(work.b_work, need_b, target_b_norm << target_k)
        if (
            target_a <= work.a_work
            and target_b <= work.b_work
            and target_k <= ks
            and target_a_norm <= work.a_norm_work
            and target_b_norm <= work.b_norm_work
        ):
            break
        seed_expand_rounds += 1
        search_stats["seed_auto_expand_trigger"] = search_stats.get("seed_auto_expand_trigger", 0) + 1
        work = StageWorkBudget(
            a_work=target_a,
            b_work=target_b,
            a_norm_work=target_a_norm,
            b_norm_work=target_b_norm,
        )
        ks = target_k
        stage_logs.append(
            {
                "type": "seed_auto_expand",
                "round": seed_expand_rounds,
                "a_max": work.a_work,
                "b_max": work.b_work,
                "a_norm": work.a_norm_work,
                "b_norm": work.b_norm_work,
                "k_max": ks,
                "seed_stats": dict(seed_stats),
            }
        )

    return SeedExpandResult(
        graph=g,
        corner_ids=list(corner_ids),
        k_start_effective=ks,
        budget=work,
        seed_expand_rounds=seed_expand_rounds,
        stage_logs=stage_logs,
    )


def run_staged_search(
    g,
    corner_ids: List[int],
    *,
    clone_graph,
    search_stage,
    make_grid_graph,
    remap_graph_to_new_grid,
    corner_score,
    kawasaki_score,
    graph_stats,
    stage_deps: StageSearchDeps,
    stage_config: StageSearchConfig,
    search_stats: Dict[str, int],
    ks: int,
    k_max: int,
    budget: StageWorkBudget,
    preferred_dir_hints: Optional[Dict[tuple, List[int]]] = None,
) -> StagedSearchResult:
    stage_logs: List[Dict[str, object]] = []
    best = clone_graph(g)
    effective_k = ks
    cids = list(corner_ids)
    cur_g = g
    work = budget

    def run_stage_round(
        *,
        stage_graph,
        stage_corner_ids: List[int],
        stage_k: int,
        stage_budget: StageWorkBudget,
    ) -> StageSearchResult:
        return search_stage(
            stage_graph,
            corner_stage=stage_corner_ids,
            stage_k=stage_k,
            deps=stage_deps,
            config=stage_config,
            budget=stage_budget,
            search_stats=search_stats,
            preferred_dir_hints=preferred_dir_hints,
        )

    if stage_config.staged_k_relax:
        for kcur in range(ks, k_max + 1):
            if kcur > ks:
                work = work.enforce_k_floor(kcur)
                ng, ncorner_ids = make_grid_graph(
                    stage_config.corners,
                    a_max=work.a_work,
                    b_max=work.b_work,
                    k_max=kcur,
                    corner_max_deg=stage_config.corner_max_deg,
                    min_corner_lines=stage_config.min_corner_lines,
                    enforce_symmetry=stage_config.enforce_symmetry,
                    use_local_ray_dirty=stage_config.use_local_ray_dirty,
                )
                remap_graph_to_new_grid(best, ng)
                cur_g = ng
                cids = ncorner_ids
            round_result = run_stage_round(
                stage_graph=cur_g,
                stage_corner_ids=cids,
                stage_k=kcur,
                stage_budget=work,
            )
            best = round_result.graph
            cids = round_result.corner_ids
            effective_k = round_result.k
            work = round_result.budget
            stage_logs.extend(round_result.stage_logs)
            cur_g = best
            stage_logs.append(
                {
                    "k": kcur,
                    "a_max": work.a_work,
                    "b_max": work.b_work,
                    "a_norm": work.a_norm_work,
                    "b_norm": work.b_norm_work,
                    "corner_score": corner_score(
                        best,
                        corner_ids=cids,
                        max_deg=stage_config.corner_max_deg,
                        min_corner_lines=stage_config.min_corner_lines,
                    ),
                    "kawasaki_score": kawasaki_score(best, tol=stage_config.kawasaki_tol),
                    "stats": graph_stats(best),
                }
            )
    else:
        round_result = run_stage_round(
            stage_graph=cur_g,
            stage_corner_ids=cids,
            stage_k=ks,
            stage_budget=work,
        )
        best = round_result.graph
        cids = round_result.corner_ids
        effective_k = round_result.k
        work = round_result.budget
        stage_logs.extend(round_result.stage_logs)

    return StagedSearchResult(
        graph=best,
        corner_ids=cids,
        effective_k=effective_k,
        budget=work,
        stage_logs=stage_logs,
    )
