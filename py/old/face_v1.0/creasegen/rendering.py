from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


def render_pattern(
    g,
    corner_ids: Sequence[int],
    *,
    out_path: str = "_tmp_out/grid_pattern.png",
    show_order: bool = False,
    highlight_kawasaki: bool = False,
    kawasaki_tol: float = 1e-8,
    prune_axes: Optional[Sequence[Tuple[int, int, int]]] = None,
    kawasaki_target_vertex_ids,
    vertex_kawasaki_error,
) -> None:
    import matplotlib.pyplot as plt

    def _clip_line_to_unit_square(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        tol: float = 1e-12,
    ) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        dx = x2 - x1
        dy = y2 - y1
        pts: List[Tuple[float, float]] = []

        def _add_pt(px: float, py: float) -> None:
            qx = min(1.0, max(0.0, px))
            qy = min(1.0, max(0.0, py))
            for ox, oy in pts:
                if abs(ox - qx) <= 1e-9 and abs(oy - qy) <= 1e-9:
                    return
            pts.append((qx, qy))

        if abs(dx) > tol:
            t = (0.0 - x1) / dx
            y = y1 + t * dy
            if -1e-9 <= y <= 1.0 + 1e-9:
                _add_pt(0.0, y)
            t = (1.0 - x1) / dx
            y = y1 + t * dy
            if -1e-9 <= y <= 1.0 + 1e-9:
                _add_pt(1.0, y)
        if abs(dy) > tol:
            t = (0.0 - y1) / dy
            x = x1 + t * dx
            if -1e-9 <= x <= 1.0 + 1e-9:
                _add_pt(x, 0.0)
            t = (1.0 - y1) / dy
            x = x1 + t * dx
            if -1e-9 <= x <= 1.0 + 1e-9:
                _add_pt(x, 1.0)

        if len(pts) < 2:
            return None
        best_pair: Optional[Tuple[Tuple[float, float], Tuple[float, float], float]] = None
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                ax, ay = pts[i]
                bx, by = pts[j]
                d2 = (ax - bx) ** 2 + (ay - by) ** 2
                if best_pair is None or d2 > best_pair[2]:
                    best_pair = (pts[i], pts[j], d2)
        if best_pair is None:
            return None
        return best_pair[0], best_pair[1]

    fig, ax = plt.subplots(figsize=(6, 6), dpi=140)
    edges = list(g.edges)
    edges.sort(key=lambda e: g.edge_birth.get((e[0], e[1]) if e[0] < e[1] else (e[1], e[0]), 10**9))
    if show_order and edges:
        import matplotlib.cm as cm

        n = max(1, len(edges) - 1)
        cmap = cm.get_cmap("viridis")
        for idx, (i, j) in enumerate(edges):
            x1, y1 = g.points_f[i]
            x2, y2 = g.points_f[j]
            c = cmap(idx / n)
            ax.plot([x1, x2], [y1, y2], color=c, linewidth=1.6)
            ax.text((x1 + x2) * 0.5, (y1 + y2) * 0.5, str(idx), fontsize=6, color=c)
    else:
        for i, j in edges:
            x1, y1 = g.points_f[i]
            x2, y2 = g.points_f[j]
            if (i, j) in g.boundary_edges or (j, i) in g.boundary_edges:
                ax.plot([x1, x2], [y1, y2], color="#666666", linewidth=1.4)
            else:
                ax.plot([x1, x2], [y1, y2], color="black", linewidth=1.2)

    if prune_axes:
        shown4 = False
        shown6 = False
        for i, j, clen in prune_axes:
            if i not in g.active_vertices or j not in g.active_vertices:
                continue
            x1, y1 = g.points_f[i]
            x2, y2 = g.points_f[j]
            clipped = _clip_line_to_unit_square(x1, y1, x2, y2)
            if clipped is None:
                continue
            (ax1, ay1), (ax2, ay2) = clipped
            if clen == 4:
                color = "#ff006e"
                label = "prune axis (4-cycle)"
                add_label = not shown4
                shown4 = True
            elif clen == 6:
                color = "#8338ec"
                label = "prune axis (6-cycle)"
                add_label = not shown6
                shown6 = True
            else:
                color = "#ffbe0b"
                label = "prune axis"
                add_label = False
            ax.plot(
                [ax1, ax2],
                [ay1, ay2],
                linestyle="--",
                linewidth=1.1,
                color=color,
                alpha=0.9,
                zorder=2,
                label=(label if add_label else None),
            )

    corner_set = set(corner_ids)
    normal_vertices = [v for v in sorted(g.active_vertices) if v not in corner_set]
    if normal_vertices:
        nx = [g.points_f[v][0] for v in normal_vertices]
        ny = [g.points_f[v][1] for v in normal_vertices]
        ax.scatter(nx, ny, s=16, color="#3a86ff", alpha=0.8, zorder=4, label="vertices")

    if corner_ids:
        xs = [g.points_f[v][0] for v in corner_ids]
        ys = [g.points_f[v][1] for v in corner_ids]
        ax.scatter(xs, ys, s=42, color="#e63946", zorder=5, label="corners")

    if highlight_kawasaki:
        bad_vs = [v for v in kawasaki_target_vertex_ids(g) if vertex_kawasaki_error(g, v) > kawasaki_tol]
        if bad_vs:
            bx = [g.points_f[v][0] for v in bad_vs]
            by = [g.points_f[v][1] for v in bad_vs]
            ax.scatter(
                bx,
                by,
                s=62,
                marker="x",
                linewidths=1.8,
                color="#ff7f11",
                zorder=6,
                label="kawasaki violations",
            )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.2)
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)
