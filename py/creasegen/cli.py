from __future__ import annotations

import argparse

from creasegen.run_config import RunConfig


def build_parser() -> argparse.ArgumentParser:
    defaults = RunConfig()
    parser = argparse.ArgumentParser(description="Grid-based origami crease generator (standalone).")
    parser.add_argument(
        "--corners",
        type=str,
        default="(0,0);(1,1);(0,1);(1,0);(1/sqrt2,0);(1,1/sqrt2);(0,1/sqrt2);(1/sqrt2,1);(1/2,1/2)",
        help="Semicolon-separated corners, e.g. '(0,0);(1,0);(1/sqrt2,1/sqrt2)'",
    )
    parser.add_argument("--a-max", type=int, default=defaults.a_max)
    parser.add_argument("--b-max", type=int, default=defaults.b_max)
    parser.add_argument("--k-max", type=int, default=defaults.k_max)
    parser.add_argument("--corner-max-deg", type=float, default=defaults.corner_max_deg)
    parser.add_argument("--max-depth", type=int, default=defaults.max_depth)
    parser.add_argument("--branch-per-node", type=int, default=defaults.branch_per_node)
    parser.add_argument("--allow-violations", type=int, default=defaults.allow_violations)
    parser.add_argument("--max-nodes", type=int, default=defaults.max_nodes)
    parser.add_argument("--max-bounces", type=int, default=defaults.open_sink_max_bounces)
    parser.add_argument("--min-corner-lines", type=int, default=defaults.min_corner_lines)
    parser.add_argument("--kawasaki-tol", type=float, default=defaults.kawasaki_tol)
    parser.add_argument("--no-corner-kawasaki-repair", action="store_true")
    parser.add_argument("--triangle-macro", action="store_true")
    parser.add_argument("--no-require-corner-kawasaki", action="store_true")
    parser.add_argument("--staged-k-relax", action="store_true")
    parser.add_argument("--k-start", type=int, default=defaults.k_start)
    parser.add_argument("--dir-top-k", type=int, default=defaults.dir_top_k)
    parser.add_argument("--priority-top-n", type=int, default=defaults.priority_top_n)
    parser.add_argument(
        "--local-ray-dirty",
        action=argparse.BooleanOptionalAction,
        default=defaults.use_local_ray_dirty,
    )
    parser.add_argument("--stop-on-corner-clear", action="store_true")
    parser.add_argument("--show-order", action="store_true")
    parser.add_argument("--auto-expand-grid", action="store_true")
    parser.add_argument("--auto-expand-max-rounds", type=int, default=defaults.auto_expand_max_rounds)
    parser.add_argument("--expand-stall-rounds", type=int, default=defaults.expand_stall_rounds)
    parser.add_argument("--no-seed-auto-expand", action="store_true")
    parser.add_argument("--seed-auto-expand-max-rounds", type=int, default=defaults.seed_auto_expand_max_rounds)
    parser.add_argument("--no-final-prune", action="store_true")
    parser.add_argument("--final-prune-rounds", type=int, default=defaults.final_prune_rounds)
    parser.add_argument("--final-prune-max-candidates", type=int, default=defaults.final_prune_max_candidates)
    parser.add_argument("--show-prune-axes", action="store_true")
    parser.add_argument("--prune-axes-max", type=int, default=defaults.prune_axes_max)
    parser.add_argument("--no-symmetry", action="store_true")
    parser.add_argument("--no-open-sink", action="store_true")
    parser.add_argument("--no-open-sink-repair", action="store_true")
    parser.add_argument("--highlight-kawasaki", action="store_true")
    parser.add_argument("--draft-guided", action="store_true")
    parser.add_argument("--draft-max-depth", type=int, default=defaults.draft_max_depth)
    parser.add_argument("--draft-branch-per-node", type=int, default=defaults.draft_branch_per_node)
    parser.add_argument("--draft-max-nodes", type=int, default=defaults.draft_max_nodes)
    parser.add_argument("--out-path", type=str, default=defaults.out_path)
    parser.add_argument(
        "--cp-graph-path",
        type=str,
        default=defaults.cp_graph_path,
        help="Write final crease graph to cp_graph_v1 JSON.",
    )
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument(
        "--profile-name",
        type=str,
        default="default",
        help="Label for grouping reusable run conditions.",
    )
    parser.add_argument(
        "--run-request-path",
        type=str,
        default="_tmp_out/last_run_request.json",
        help="Path to save {request, profile_name, timestamp}.",
    )
    parser.add_argument(
        "--no-save-run-request",
        action="store_true",
        help="Disable saving run request JSON.",
    )
    return parser
