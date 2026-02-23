from __future__ import annotations

from typing import Dict, List, Sequence, Tuple


def apply_final_prune_rounds(
    best,
    corner_ids: Sequence[int],
    *,
    refresh_graph_by_pruning,
    global_score,
    priority_corner_kawasaki_score,
    corner_score,
    preserve_satisfied_corners,
    graph_stats,
    corner_max_deg: float,
    min_corner_lines: int,
    kawasaki_tol: float,
    enforce_symmetry: bool,
    final_prune_rounds: int,
    final_prune_max_candidates: int,
    half,
    search_stats: Dict[str, int],
):
    stage_logs: List[Dict[str, object]] = []
    if final_prune_rounds <= 0 or final_prune_max_candidates <= 0:
        return best, stage_logs

    # Probe axis for diagnostics requested in discussion: y = -x + 0.5.
    # axis direction is +/- (1, -1) => bucket 6, and line constant is x+y=1/2.
    probe_line_key = (6, half.a, half.b, half.k)
    out_best = best
    for r in range(1, final_prune_rounds + 1):
        pruned, removed = refresh_graph_by_pruning(
            out_best,
            corner_ids=corner_ids,
            max_deg=corner_max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
            enforce_symmetry=enforce_symmetry,
            max_candidates=final_prune_max_candidates,
            stats=search_stats,
            probe_line_key=probe_line_key,
        )
        if removed <= 0:
            search_stats["final_prune_nochange"] = search_stats.get("final_prune_nochange", 0) + 1
            break
        before_sc = global_score(
            out_best,
            corner_ids=corner_ids,
            max_deg=corner_max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        after_sc = global_score(
            pruned,
            corner_ids=corner_ids,
            max_deg=corner_max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        before_ck = priority_corner_kawasaki_score(out_best, corner_ids=corner_ids, tol=kawasaki_tol)
        after_ck = priority_corner_kawasaki_score(pruned, corner_ids=corner_ids, tol=kawasaki_tol)
        before_corner = corner_score(
            out_best,
            corner_ids=corner_ids,
            max_deg=corner_max_deg,
            min_corner_lines=min_corner_lines,
        )
        after_corner = corner_score(
            pruned,
            corner_ids=corner_ids,
            max_deg=corner_max_deg,
            min_corner_lines=min_corner_lines,
        )
        global_nonworse = (
            after_sc[0] <= before_sc[0]
            and after_sc[3] <= before_sc[3] + 1e-12
        )
        corner_nonworse = (
            after_corner[0] <= before_corner[0]
            and after_corner[1] <= before_corner[1]
            and after_corner[2] <= before_corner[2] + 1e-12
            and after_corner[3] <= before_corner[3] + 1e-12
        )
        keep_satisfied = preserve_satisfied_corners(
            out_best,
            pruned,
            corner_ids=corner_ids,
            max_deg=corner_max_deg,
            min_corner_lines=min_corner_lines,
        )
        if global_nonworse and corner_nonworse and keep_satisfied and after_ck <= before_ck:
            out_best = pruned
            search_stats["final_prune_applied_rounds"] = search_stats.get("final_prune_applied_rounds", 0) + 1
            search_stats["final_prune_removed_edges"] = search_stats.get("final_prune_removed_edges", 0) + removed
            stage_logs.append(
                {
                    "type": "final_prune",
                    "round": r,
                    "removed_edges": removed,
                    "score": after_sc,
                    "priority_corner_kawasaki": after_ck,
                    "stats": graph_stats(out_best),
                }
            )
            continue
        if not corner_nonworse or not keep_satisfied:
            search_stats["final_prune_reject_corner_break"] = search_stats.get("final_prune_reject_corner_break", 0) + 1
        search_stats["final_prune_reject_worse"] = search_stats.get("final_prune_reject_worse", 0) + 1
        # Do not stop final prune on a single rejected proposal.
        # Keep trying subsequent prune rounds.
        continue

    return out_best, stage_logs
