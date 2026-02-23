from __future__ import annotations

from typing import Optional, Tuple

from creasegen.direction import _cross_f


def _ray_segment_hit_float(
    origin: Tuple[float, float],
    d: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    eps: float = 1e-12,
) -> Optional[Tuple[float, float]]:
    ox, oy = origin
    dx, dy = d
    ax, ay = a
    bx, by = b

    vx = bx - ax
    vy = by - ay
    denom = dx * vy - dy * vx
    if -eps <= denom <= eps:
        return None

    wx = ax - ox
    wy = ay - oy
    t = (wx * vy - wy * vx) / denom
    if t <= eps:
        return None

    u = (wx * dy - wy * dx) / denom
    if u < -eps or u > 1.0 + eps:
        return None
    return (t, u)


def _ray_segment_hit_t_float(
    origin: Tuple[float, float],
    d: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    eps: float = 1e-12,
) -> Optional[float]:
    ox, oy = origin
    dx, dy = d
    ax, ay = a
    bx, by = b

    vx = bx - ax
    vy = by - ay
    denom = dx * vy - dy * vx
    if -eps <= denom <= eps:
        return None

    wx = ax - ox
    wy = ay - oy
    t = (wx * vy - wy * vx) / denom
    if t <= eps:
        return None

    u = (wx * dy - wy * dx) / denom
    if u < -eps or u > 1.0 + eps:
        return None
    return t


def _is_point_on_line(
    a: Tuple[float, float],
    b: Tuple[float, float],
    p: Tuple[float, float],
    tol: float = 1e-8,
) -> bool:
    abx, aby = b[0] - a[0], b[1] - a[1]
    apx, apy = p[0] - a[0], p[1] - a[1]
    return abs(_cross_f(abx, aby, apx, apy)) <= tol


def _strict_segments_intersect(
    a1: Tuple[float, float],
    a2: Tuple[float, float],
    b1: Tuple[float, float],
    b2: Tuple[float, float],
    eps: float = 1e-10,
) -> bool:
    def orient(p: Tuple[float, float], q: Tuple[float, float], r: Tuple[float, float]) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a1, a2, b1)
    o2 = orient(a1, a2, b2)
    o3 = orient(b1, b2, a1)
    o4 = orient(b1, b2, a2)
    # strict interior crossing only
    return (o1 * o2 < -eps) and (o3 * o4 < -eps)


def _collinear_overlap_length(
    a1: Tuple[float, float],
    a2: Tuple[float, float],
    b1: Tuple[float, float],
    b2: Tuple[float, float],
    eps: float = 1e-10,
) -> float:
    # Return overlap length on collinear segments; 0 if not collinear/non-overlapping.
    abx = a2[0] - a1[0]
    aby = a2[1] - a1[1]
    if abs(_cross_f(abx, aby, b1[0] - a1[0], b1[1] - a1[1])) > eps:
        return 0.0
    if abs(_cross_f(abx, aby, b2[0] - a1[0], b2[1] - a1[1])) > eps:
        return 0.0

    # Project onto dominant axis for robust interval overlap.
    if abs(abx) >= abs(aby):
        x1, x2 = sorted((a1[0], a2[0]))
        y1, y2 = sorted((b1[0], b2[0]))
        lo = max(x1, y1)
        hi = min(x2, y2)
        return max(0.0, hi - lo)
    x1, x2 = sorted((a1[1], a2[1]))
    y1, y2 = sorted((b1[1], b2[1]))
    lo = max(x1, y1)
    hi = min(x2, y2)
    return max(0.0, hi - lo)


def _crosses_existing_edges(g, i: int, j: int) -> bool:
    ai = g.points_f[i]
    bj = g.points_f[j]
    for u, v in g.edges:
        if u in (i, j) or v in (i, j):
            continue
        pu = g.points_f[u]
        pv = g.points_f[v]
        if _strict_segments_intersect(ai, bj, pu, pv):
            return True
    return False

