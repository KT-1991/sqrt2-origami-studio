from __future__ import annotations

from typing import Dict, List, Tuple

__all__ = [
    "RUN_RESULT_KEYS",
    "build_run_result",
]


RUN_RESULT_KEYS: Tuple[str, ...] = (
    "sec",
    "params",
    "stats_before",
    "stats_after",
    "lattice_bounds_after",
    "corner_score_before",
    "corner_score_after",
    "kawasaki_score_before",
    "kawasaki_score_after",
    "priority_corner_kawasaki_before",
    "priority_corner_kawasaki_after",
    "corner_errors_after",
    "corner_line_counts_after",
    "corner_lowline_after",
    "corner_violations_after",
    "kawasaki_violations_after",
    "priority_corner_kawasaki_violations_after",
    "prune_axes_count",
    "probe_axis_y_minus_x_half_key",
    "probe_axis_y_minus_x_half_present_rounds",
    "probe_axis_y_minus_x_half_targeted_rounds",
    "probe_axis_y_minus_x_half_attempted",
    "probe_axis_y_minus_x_half_fail_tx",
    "probe_axis_y_minus_x_half_reject_score",
    "probe_axis_y_minus_x_half_accepted",
    "search_stats",
    "stage_logs",
    "out_path",
)


def _validate_run_result_schema(result: Dict[str, object]) -> None:
    keys_now = tuple(result.keys())
    if keys_now != RUN_RESULT_KEYS:
        raise ValueError(
            "run result schema mismatch: expected keys "
            f"{RUN_RESULT_KEYS} but got {keys_now}"
        )


def build_run_result(
    *,
    elapsed_sec: float,
    params: Dict[str, object],
    before_stats: Dict[str, int],
    graph_stats_after: Dict[str, int],
    lattice_bounds_after: Dict[str, int],
    corner_score_before: Tuple[int, int, float, float],
    corner_score_after: Tuple[int, int, float, float],
    kawasaki_score_before: Tuple[int, float, int],
    kawasaki_score_after: Tuple[int, float, int],
    priority_corner_kawasaki_before: Tuple[int, float],
    priority_corner_kawasaki_after: Tuple[int, float],
    corner_errors_after: List[float],
    corner_line_counts_after: List[int],
    min_corner_lines: int,
    prune_axes_count: int,
    half,
    search_stats: Dict[str, int],
    stage_logs: List[Dict[str, object]],
    staged_k_relax: bool,
    auto_expand_grid: bool,
    render_image: bool,
    out_path: str,
) -> Dict[str, object]:
    result = {
        "sec": round(elapsed_sec, 3),
        "params": params,
        "stats_before": before_stats,
        "stats_after": graph_stats_after,
        "lattice_bounds_after": lattice_bounds_after,
        "corner_score_before": corner_score_before,
        "corner_score_after": corner_score_after,
        "kawasaki_score_before": kawasaki_score_before,
        "kawasaki_score_after": kawasaki_score_after,
        "priority_corner_kawasaki_before": priority_corner_kawasaki_before,
        "priority_corner_kawasaki_after": priority_corner_kawasaki_after,
        "corner_errors_after": corner_errors_after,
        "corner_line_counts_after": corner_line_counts_after,
        "corner_lowline_after": sum(1 for c in corner_line_counts_after if c < min_corner_lines),
        "corner_violations_after": sum(1 for e in corner_errors_after if e > 1e-12),
        "kawasaki_violations_after": kawasaki_score_after[0],
        "priority_corner_kawasaki_violations_after": priority_corner_kawasaki_after[0],
        "prune_axes_count": prune_axes_count,
        "probe_axis_y_minus_x_half_key": [6, half.a, half.b, half.k],
        "probe_axis_y_minus_x_half_present_rounds": search_stats.get("prune_probe_line_present", 0),
        "probe_axis_y_minus_x_half_targeted_rounds": search_stats.get("prune_probe_line_targeted", 0),
        "probe_axis_y_minus_x_half_attempted": search_stats.get("prune_probe_line_attempted", 0),
        "probe_axis_y_minus_x_half_fail_tx": search_stats.get("prune_probe_line_fail_tx", 0),
        "probe_axis_y_minus_x_half_reject_score": search_stats.get("prune_probe_line_reject_score", 0),
        "probe_axis_y_minus_x_half_accepted": search_stats.get("prune_probe_line_accepted", 0),
        "search_stats": search_stats,
        "stage_logs": stage_logs if (staged_k_relax or auto_expand_grid or len(stage_logs) > 0) else None,
        "out_path": out_path if render_image else None,
    }
    _validate_run_result_schema(result)
    return result
