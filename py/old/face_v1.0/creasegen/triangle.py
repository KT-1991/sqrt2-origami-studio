from __future__ import annotations

from typing import Dict, List, Optional, Set


def add_segment_with_splits_ids(
    g,
    start_v: int,
    goal_v: int,
    *,
    exact_dir_idx_from_delta,
    crosses_existing_edges,
    is_point_on_line,
    max_steps: int = 32,
    stats: Optional[Dict[str, int]] = None,
) -> bool:
    if start_v == goal_v:
        return False
    p0 = g.points[start_v]
    p1 = g.points[goal_v]
    d0 = exact_dir_idx_from_delta(p1.x - p0.x, p1.y - p0.y)
    if d0 is None:
        return False
    changed = False
    cur = start_v
    a = g.points_f[start_v]
    b = g.points_f[goal_v]
    seen: Set[int] = {cur}
    for _ in range(max_steps):
        if cur == goal_v:
            return changed
        if g._norm_edge(cur, goal_v) in g.edges:
            return True
        # For seeding, prefer finishing by a direct segment when no interior crossing exists.
        # This avoids open-sink style overshoot when the goal corner is currently isolated.
        if not crosses_existing_edges(g, cur, goal_v):
            g.add_edge(cur, goal_v, boundary=False)
            if g._norm_edge(cur, goal_v) in g.edges:
                return True
        hit = g.shoot_ray_and_split(cur, d0, stats=stats)
        if hit is None:
            return False
        _, nxt = hit
        if nxt == cur:
            return False
        if not is_point_on_line(a, b, g.points_f[nxt], tol=1e-7):
            return False
        changed = True
        cur = nxt
        if cur in seen:
            return False
        seen.add(cur)
    return False


def apply_triangle_macro_variants(
    g,
    anchor_v: int,
    *,
    add_segment_with_splits_ids_fn,
    clone_graph,
    diagonal_symmetry_ok,
    graph_state_key,
    exact_dir_idx_from_delta,
    enforce_symmetry: bool = True,
    max_other_vertices: int = 6,
    max_centers: int = 3,
) -> List:
    ax, ay = g.points_f[anchor_v]
    if enforce_symmetry and ax > ay + 1e-10:
        return []

    others = [v for v in g.active_vertices if v != anchor_v]
    others.sort(key=lambda v: (g.points_f[v][0] - ax) ** 2 + (g.points_f[v][1] - ay) ** 2)
    others = others[:max_other_vertices]

    out = []
    seen: Set[tuple] = set()
    center_pool = [v for v in g.active_vertices if v != anchor_v]
    for i in range(len(others)):
        for j in range(i + 1, len(others)):
            vA = anchor_v
            vB = others[i]
            vC = others[j]
            trip = [vA, vB, vC]
            cx = sum(g.points_f[v][0] for v in trip) / 3.0
            cy = sum(g.points_f[v][1] for v in trip) / 3.0
            centers = sorted(
                center_pool,
                key=lambda v: (g.points_f[v][0] - cx) ** 2 + (g.points_f[v][1] - cy) ** 2,
            )[:max_centers]
            for c in centers:
                if c in trip:
                    continue
                # Require 16-direction alignments from launch vertices to center.
                ok = True
                for sv in trip:
                    p = g.points[sv]
                    q = g.points[c]
                    if exact_dir_idx_from_delta(q.x - p.x, q.y - p.y) is None:
                        ok = False
                        break
                if not ok:
                    continue
                h = clone_graph(g)
                changed = False
                for sv in trip:
                    changed = add_segment_with_splits_ids_fn(h, sv, c) or changed
                if enforce_symmetry:
                    mc = h.mirror_vertex_idx(c)
                    if mc is None:
                        continue
                    for sv in trip:
                        msv = h.mirror_vertex_idx(sv)
                        if msv is None:
                            changed = False
                            break
                        changed = add_segment_with_splits_ids_fn(h, msv, mc) or changed
                    if not diagonal_symmetry_ok(h):
                        continue
                if not changed:
                    continue
                k = graph_state_key(h)
                if k in seen:
                    continue
                seen.add(k)
                out.append(h)
    return out
