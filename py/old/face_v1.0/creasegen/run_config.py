from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, Tuple


_SEED_EXPAND_FIELDS: Tuple[str, ...] = (
    "staged_k_relax",
    "k_start",
    "k_max",
    "a_max",
    "b_max",
    "seed_auto_expand",
    "seed_auto_expand_max_rounds",
    "enforce_symmetry",
    "use_local_ray_dirty",
)

_FINAL_PRUNE_FIELDS: Tuple[str, ...] = (
    "corner_max_deg",
    "min_corner_lines",
    "kawasaki_tol",
    "enforce_symmetry",
    "final_prune_rounds",
    "final_prune_max_candidates",
)

_RESULT_PARAM_FIELDS: Tuple[str, ...] = (
    "a_max",
    "b_max",
    "k_max",
    "corner_max_deg",
    "max_depth",
    "branch_per_node",
    "allow_violations",
    "max_nodes",
    "enforce_symmetry",
    "enable_open_sink",
    "enable_open_sink_repair",
    "open_sink_max_bounces",
    "min_corner_lines",
    "kawasaki_tol",
    "enable_corner_kawasaki_repair",
    "enable_triangle_macro",
    "require_corner_kawasaki",
    "staged_k_relax",
    "k_start",
    "dir_top_k",
    "priority_top_n",
    "use_local_ray_dirty",
    "stop_on_corner_clear",
    "auto_expand_grid",
    "auto_expand_max_rounds",
    "expand_stall_rounds",
    "seed_auto_expand",
    "seed_auto_expand_max_rounds",
    "final_prune",
    "final_prune_rounds",
    "final_prune_max_candidates",
    "show_prune_axes",
    "prune_axes_max",
    "show_order",
    "highlight_kawasaki",
)


@dataclass(frozen=True)
class RunConfig:
    a_max: int = 2
    b_max: int = 2
    k_max: int = 2
    corner_max_deg: float = 45.0
    max_depth: int = 6
    branch_per_node: int = 4
    allow_violations: int = 2
    max_nodes: int = 300
    enforce_symmetry: bool = True
    enable_open_sink: bool = True
    enable_open_sink_repair: bool = True
    open_sink_max_bounces: int = 14
    min_corner_lines: int = 2
    kawasaki_tol: float = 1e-8
    enable_corner_kawasaki_repair: bool = True
    enable_triangle_macro: bool = False
    require_corner_kawasaki: bool = True
    staged_k_relax: bool = False
    k_start: int = 1
    dir_top_k: int = 4
    priority_top_n: int = 6
    use_local_ray_dirty: bool = False
    stop_on_corner_clear: bool = False
    auto_expand_grid: bool = False
    auto_expand_max_rounds: int = 3
    expand_stall_rounds: int = 1
    seed_auto_expand: bool = True
    seed_auto_expand_max_rounds: int = 1
    final_prune: bool = True
    final_prune_rounds: int = 2
    final_prune_max_candidates: int = 64
    show_prune_axes: bool = False
    prune_axes_max: int = 24
    show_order: bool = False
    highlight_kawasaki: bool = False
    render_image: bool = True
    out_path: str = "_tmp_out/grid_pattern.png"

    @classmethod
    def from_cli_args(cls, args) -> "RunConfig":
        return cls(
            a_max=args.a_max,
            b_max=args.b_max,
            k_max=args.k_max,
            corner_max_deg=args.corner_max_deg,
            max_depth=args.max_depth,
            branch_per_node=args.branch_per_node,
            allow_violations=args.allow_violations,
            max_nodes=args.max_nodes,
            enforce_symmetry=not args.no_symmetry,
            enable_open_sink=not args.no_open_sink,
            enable_open_sink_repair=not args.no_open_sink_repair,
            open_sink_max_bounces=args.max_bounces,
            min_corner_lines=args.min_corner_lines,
            kawasaki_tol=args.kawasaki_tol,
            enable_corner_kawasaki_repair=not args.no_corner_kawasaki_repair,
            enable_triangle_macro=args.triangle_macro,
            require_corner_kawasaki=not args.no_require_corner_kawasaki,
            staged_k_relax=args.staged_k_relax,
            k_start=args.k_start,
            dir_top_k=args.dir_top_k,
            priority_top_n=args.priority_top_n,
            use_local_ray_dirty=args.local_ray_dirty,
            stop_on_corner_clear=args.stop_on_corner_clear,
            auto_expand_grid=args.auto_expand_grid,
            auto_expand_max_rounds=args.auto_expand_max_rounds,
            expand_stall_rounds=args.expand_stall_rounds,
            seed_auto_expand=not args.no_seed_auto_expand,
            seed_auto_expand_max_rounds=args.seed_auto_expand_max_rounds,
            final_prune=not args.no_final_prune,
            final_prune_rounds=args.final_prune_rounds,
            final_prune_max_candidates=args.final_prune_max_candidates,
            show_prune_axes=args.show_prune_axes,
            prune_axes_max=args.prune_axes_max,
            show_order=args.show_order,
            highlight_kawasaki=args.highlight_kawasaki,
            render_image=not args.no_render,
            out_path=args.out_path,
        )

    def _select(self, names: Sequence[str]) -> Dict[str, object]:
        return {name: getattr(self, name) for name in names}

    def seed_expand_kwargs(self) -> Dict[str, object]:
        return self._select(_SEED_EXPAND_FIELDS)

    def final_prune_kwargs(self) -> Dict[str, object]:
        return self._select(_FINAL_PRUNE_FIELDS)

    def result_params(
        self,
        *,
        a_work: int,
        b_work: int,
        a_norm_work: int,
        b_norm_work: int,
        effective_k: int,
        seed_expand_rounds: int,
    ) -> Dict[str, object]:
        out = self._select(_RESULT_PARAM_FIELDS)
        out.update(
            {
                "a_max_effective": a_work,
                "b_max_effective": b_work,
                "a_norm_effective": a_norm_work,
                "b_norm_effective": b_norm_work,
                "k_max_effective": effective_k,
                "seed_expand_rounds_used": seed_expand_rounds,
            }
        )
        return out

    def run_request_payload(self, corners_expr: str) -> Dict[str, object]:
        return {
            "corners": corners_expr,
            "a_max": self.a_max,
            "b_max": self.b_max,
            "k_max": self.k_max,
            "corner_max_deg": self.corner_max_deg,
            "max_depth": self.max_depth,
            "branch_per_node": self.branch_per_node,
            "allow_violations": self.allow_violations,
            "max_nodes": self.max_nodes,
            "max_bounces": self.open_sink_max_bounces,
            "min_corner_lines": self.min_corner_lines,
            "kawasaki_tol": self.kawasaki_tol,
            "no_corner_kawasaki_repair": (not self.enable_corner_kawasaki_repair),
            "triangle_macro": self.enable_triangle_macro,
            "no_require_corner_kawasaki": (not self.require_corner_kawasaki),
            "staged_k_relax": self.staged_k_relax,
            "k_start": self.k_start,
            "dir_top_k": self.dir_top_k,
            "priority_top_n": self.priority_top_n,
            "local_ray_dirty": self.use_local_ray_dirty,
            "stop_on_corner_clear": self.stop_on_corner_clear,
            "show_order": self.show_order,
            "auto_expand_grid": self.auto_expand_grid,
            "auto_expand_max_rounds": self.auto_expand_max_rounds,
            "expand_stall_rounds": self.expand_stall_rounds,
            "no_seed_auto_expand": (not self.seed_auto_expand),
            "seed_auto_expand_max_rounds": self.seed_auto_expand_max_rounds,
            "no_final_prune": (not self.final_prune),
            "final_prune_rounds": self.final_prune_rounds,
            "final_prune_max_candidates": self.final_prune_max_candidates,
            "show_prune_axes": self.show_prune_axes,
            "prune_axes_max": self.prune_axes_max,
            "no_symmetry": (not self.enforce_symmetry),
            "no_open_sink": (not self.enable_open_sink),
            "no_open_sink_repair": (not self.enable_open_sink_repair),
            "highlight_kawasaki": self.highlight_kawasaki,
            "out_path": self.out_path,
            "no_render": (not self.render_image),
        }
