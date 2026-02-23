from __future__ import annotations

from math import atan2, pi
from typing import List, Sequence, Tuple


def incident_angles(g, v_idx: int, include_boundary: bool = False) -> List[float]:
    vx, vy = g.points_f[v_idx]
    out: List[float] = []
    for u in g.adj.get(v_idx, set()):
        e = (v_idx, u) if v_idx < u else (u, v_idx)
        if not include_boundary and e in g.boundary_edges:
            continue
        ux, uy = g.points_f[u]
        a = atan2(uy - vy, ux - vx)
        if a < 0:
            a += 2 * pi
        out.append(a)
    out.sort()
    return out


def unique_angles(angles: Sequence[float], tol: float = 1e-10) -> List[float]:
    if not angles:
        return []
    arr = sorted(angles)
    out = [arr[0]]
    for a in arr[1:]:
        if abs(a - out[-1]) > tol:
            out.append(a)
    if len(out) >= 2 and abs((out[0] + 2 * pi) - out[-1]) <= tol:
        out.pop()
    return out


def _norm_angle(a: float) -> float:
    x = a % (2 * pi)
    if x < 0:
        x += 2 * pi
    return x


def _interior_wedge(px: float, py: float, eps: float = 1e-12) -> Tuple[float, float]:
    on_l = abs(px - 0.0) <= eps
    on_r = abs(px - 1.0) <= eps
    on_b = abs(py - 0.0) <= eps
    on_t = abs(py - 1.0) <= eps
    if on_l and on_b:
        return (0.0, pi / 2)
    if on_r and on_b:
        return (pi / 2, pi / 2)
    if on_r and on_t:
        return (pi, pi / 2)
    if on_l and on_t:
        return (3 * pi / 2, pi / 2)
    if on_b:
        return (0.0, pi)
    if on_t:
        return (pi, pi)
    if on_l:
        return (3 * pi / 2, pi)
    if on_r:
        return (pi / 2, pi)
    return (0.0, 2 * pi)


def corner_sectors(g, v_idx: int) -> List[float]:
    px, py = g.points_f[v_idx]
    start, width = _interior_wedge(px, py)
    angs = unique_angles(incident_angles(g, v_idx, include_boundary=False))
    ts: List[float] = [0.0, width]
    for a in angs:
        t = _norm_angle(a - start)
        if -1e-12 <= t <= width + 1e-12:
            ts.append(min(max(t, 0.0), width))
    ts = unique_angles(sorted(ts))
    if len(ts) <= 1:
        return []
    out: List[float] = []
    if width >= 2 * pi - 1e-10:
        for i in range(len(ts)):
            a = ts[i]
            b = ts[(i + 1) % len(ts)]
            d = b - a
            if d <= 0:
                d += 2 * pi
            out.append(d)
        return out
    for i in range(len(ts) - 1):
        out.append(ts[i + 1] - ts[i])
    return out


def corner_condition_error(g, v_idx: int, max_deg: float) -> float:
    thr = max_deg * pi / 180.0
    secs = corner_sectors(g, v_idx)
    return sum(max(0.0, s - thr) for s in secs)


def corner_line_count(g, v_idx: int) -> int:
    cnt = 0
    for u in g.adj.get(v_idx, set()):
        e = (v_idx, u) if v_idx < u else (u, v_idx)
        if e in g.boundary_edges:
            continue
        cnt += 1
    return cnt


def corner_score(
    g,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int = 2,
) -> Tuple[int, int, float, float]:
    errs = [corner_condition_error(g, v, max_deg=max_deg) for v in corner_ids]
    bad = sum(1 for e in errs if e > 1e-12)
    lowdeg = 0
    lowdeg_pen = 0.0
    for v in corner_ids:
        deficit = max(0, min_corner_lines - corner_line_count(g, v))
        if deficit > 0:
            lowdeg += 1
            lowdeg_pen += float(deficit)
    return (bad, lowdeg, sum(errs), lowdeg_pen)

