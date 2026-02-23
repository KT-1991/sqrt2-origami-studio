from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from fractions import Fraction
from math import atan2, pi
from typing import Dict, List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class Qsqrt2:
    a: Fraction
    b: Fraction

    @staticmethod
    def from_int(n: int) -> "Qsqrt2":
        return Qsqrt2(Fraction(n), Fraction(0))

    @staticmethod
    def from_fraction(x: Fraction) -> "Qsqrt2":
        return Qsqrt2(x, Fraction(0))

    def __add__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(self.a + o.a, self.b + o.b)

    def __sub__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(self.a - o.a, self.b - o.b)

    def __mul__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(self.a * o.a + 2 * self.b * o.b, self.a * o.b + self.b * o.a)

    def __neg__(self) -> "Qsqrt2":
        return Qsqrt2(-self.a, -self.b)

    def __truediv__(self, o: "Qsqrt2") -> "Qsqrt2":
        den = o.a * o.a - 2 * o.b * o.b
        if den == 0:
            raise ZeroDivisionError("singular Qsqrt2 inverse")
        inv = Qsqrt2(o.a / den, -o.b / den)
        return self * inv

    def approx(self) -> float:
        return float(self.a) + float(self.b) * (2.0**0.5)


ZERO = Qsqrt2.from_int(0)
ONE = Qsqrt2.from_int(1)
HALF = Qsqrt2.from_fraction(Fraction(1, 2))
INV_SQRT2 = Qsqrt2(Fraction(0), Fraction(1, 2))
SQRT2_MINUS_ONE = Qsqrt2(Fraction(-1), Fraction(1))


@dataclass(frozen=True)
class PointE:
    x: Qsqrt2
    y: Qsqrt2

    def approx(self) -> Tuple[float, float]:
        return (self.x.approx(), self.y.approx())


ANGLE_COUNT = 16
_S = SQRT2_MINUS_ONE
DIRS: List[Tuple[Qsqrt2, Qsqrt2]] = [
    (ONE, ZERO),
    (ONE, _S),
    (ONE, ONE),
    (_S, ONE),
    (ZERO, ONE),
    (-_S, ONE),
    (-ONE, ONE),
    (-ONE, _S),
    (-ONE, ZERO),
    (-ONE, -_S),
    (-ONE, -ONE),
    (-_S, -ONE),
    (ZERO, -ONE),
    (_S, -ONE),
    (ONE, -ONE),
    (ONE, -_S),
]
DIRS_F: List[Tuple[float, float]] = [(dx.approx(), dy.approx()) for dx, dy in DIRS]


def _q2_sign(z: Qsqrt2) -> int:
    a = z.a
    b = z.b
    if a == 0 and b == 0:
        return 0
    if b == 0:
        return 1 if a > 0 else -1
    if a == 0:
        return 1 if b > 0 else -1
    sa = 1 if a > 0 else -1
    sb = 1 if b > 0 else -1
    if sa == sb:
        return sa
    aa = a * a
    bb2 = 2 * b * b
    if sa > 0 and sb < 0:
        return 1 if aa > bb2 else -1
    return 1 if bb2 > aa else -1


def _q2_cmp(x: Qsqrt2, y: Qsqrt2) -> int:
    return _q2_sign(x - y)


def _in_square(p: PointE) -> bool:
    return (
        _q2_cmp(p.x, ZERO) >= 0
        and _q2_cmp(p.x, ONE) <= 0
        and _q2_cmp(p.y, ZERO) >= 0
        and _q2_cmp(p.y, ONE) <= 0
    )


def _point_key(p: PointE) -> Tuple[Fraction, Fraction, Fraction, Fraction]:
    return (p.x.a, p.x.b, p.y.a, p.y.b)


def _v2_of_denominator(fr: Fraction) -> Optional[int]:
    d = fr.denominator
    k = 0
    while d % 2 == 0:
        d //= 2
        k += 1
    if d != 1:
        return None
    return k


def _point_k_level(p: PointE) -> Optional[int]:
    ka_x = _v2_of_denominator(p.x.a)
    kb_x = _v2_of_denominator(p.x.b)
    ka_y = _v2_of_denominator(p.y.a)
    kb_y = _v2_of_denominator(p.y.b)
    if ka_x is None or kb_x is None or ka_y is None or kb_y is None:
        return None
    return max(ka_x, kb_x, ka_y, kb_y)


def _cross(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2) -> Qsqrt2:
    return ax * by - ay * bx


def _dot(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2) -> Qsqrt2:
    return ax * bx + ay * by


def _ray_segment_hit(
    origin: PointE,
    d: Tuple[Qsqrt2, Qsqrt2],
    a: PointE,
    b: PointE,
) -> Optional[Tuple[Qsqrt2, Qsqrt2, PointE]]:
    vx = b.x - a.x
    vy = b.y - a.y
    dx, dy = d
    denom = _cross(dx, dy, vx, vy)
    if denom == ZERO:
        return None
    wx = a.x - origin.x
    wy = a.y - origin.y
    t = _cross(wx, wy, vx, vy) / denom
    u = _cross(wx, wy, dx, dy) / denom
    if _q2_cmp(t, ZERO) <= 0:
        return None
    if _q2_cmp(u, ZERO) < 0 or _q2_cmp(u, ONE) > 0:
        return None
    p = PointE(origin.x + t * dx, origin.y + t * dy)
    return (t, u, p)


def mirror_point_y_eq_x(p: PointE) -> PointE:
    return PointE(p.y, p.x)


def mirrored_dir_idx(dir_idx: int) -> int:
    return (4 - dir_idx) % ANGLE_COUNT


def _cross_f(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


def _ray_segment_hit_float(
    origin: Tuple[float, float],
    d: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    eps: float = 1e-12,
) -> Optional[Tuple[float, float]]:
    vx = b[0] - a[0]
    vy = b[1] - a[1]
    dx, dy = d
    denom = _cross_f(dx, dy, vx, vy)
    if abs(denom) <= eps:
        return None
    wx = a[0] - origin[0]
    wy = a[1] - origin[1]
    t = _cross_f(wx, wy, vx, vy) / denom
    u = _cross_f(wx, wy, dx, dy) / denom
    if t <= eps:
        return None
    if u < -eps or u > 1.0 + eps:
        return None
    return (t, u)


def _angle_of_dir_idx(d: int) -> float:
    dx, dy = DIRS_F[d]
    a = atan2(dy, dx)
    if a < 0:
        a += 2 * pi
    return a


def _in_ccw_interval(a: float, start: float, end: float, tol: float = 1e-10) -> bool:
    a = _norm_angle(a)
    start = _norm_angle(start)
    end = _norm_angle(end)
    if start <= end:
        return start - tol <= a <= end + tol
    return a >= start - tol or a <= end + tol


def _nearest_dir_idx(dx: float, dy: float) -> int:
    n = (dx * dx + dy * dy) ** 0.5
    if n <= 1e-15:
        return 0
    ux, uy = dx / n, dy / n
    best_k = 0
    best_dot = -1e100
    for k, (rx, ry) in enumerate(DIRS_F):
        rn = (rx * rx + ry * ry) ** 0.5
        if rn <= 1e-15:
            continue
        dot = ux * (rx / rn) + uy * (ry / rn)
        if dot > best_dot:
            best_dot = dot
            best_k = k
    return best_k


def _reflected_dir_idx(cur_d: int, a: Tuple[float, float], b: Tuple[float, float]) -> int:
    tx = b[0] - a[0]
    ty = b[1] - a[1]
    n = (tx * tx + ty * ty) ** 0.5
    if n <= 1e-15:
        return cur_d
    tx /= n
    ty /= n
    vx, vy = DIRS_F[cur_d]
    dot = vx * tx + vy * ty
    # Open-sink reflection rule: flip tangent component.
    rx = vx - 2.0 * dot * tx
    ry = vy - 2.0 * dot * ty
    return _nearest_dir_idx(rx, ry)


def _reflected_dir_idx_by_axis_dir(cur_d: int, axis_d: int) -> int:
    tx, ty = DIRS_F[axis_d]
    n = (tx * tx + ty * ty) ** 0.5
    if n <= 1e-15:
        return cur_d
    tx /= n
    ty /= n
    vx, vy = DIRS_F[cur_d]
    dot = vx * tx + vy * ty
    rx = vx - 2.0 * dot * tx
    ry = vy - 2.0 * dot * ty
    return _nearest_dir_idx(rx, ry)


def _symmetric_candidate_dirs(
    used_dirs: Sequence[int],
    admissible: Sequence[int],
    incoming_d: Optional[int] = None,
) -> List[int]:
    used = sorted(set(used_dirs))
    if not used:
        return []
    admissible_set = set(admissible)
    out: Set[int] = set()
    if incoming_d is not None:
        for axis in used:
            d = _reflected_dir_idx_by_axis_dir(incoming_d, axis)
            if d in admissible_set and d not in used:
                out.add(d)
    else:
        for base in used:
            for axis in used:
                d = _reflected_dir_idx_by_axis_dir(base, axis)
                if d in admissible_set and d not in used:
                    out.add(d)
    return sorted(out)


def enumerate_grid_points(
    a_max: int,
    b_max: int,
    k_max: int,
) -> Tuple[List[PointE], Dict[Tuple[Fraction, Fraction, Fraction, Fraction], int]]:
    xvals: Dict[Tuple[Fraction, Fraction], Qsqrt2] = {}
    for k in range(k_max + 1):
        den = Fraction(1, 2**k)
        for a in range(-a_max, a_max + 1):
            for b in range(-b_max, b_max + 1):
                z = Qsqrt2(Fraction(a) * den, Fraction(b) * den)
                if _q2_cmp(z, ZERO) >= 0 and _q2_cmp(z, ONE) <= 0:
                    xvals[(z.a, z.b)] = z
    xs = list(xvals.values())
    points: List[PointE] = []
    p2i: Dict[Tuple[Fraction, Fraction, Fraction, Fraction], int] = {}
    for x in xs:
        for y in xs:
            p = PointE(x, y)
            idx = len(points)
            points.append(p)
            p2i[_point_key(p)] = idx
    return points, p2i


class GridCreaseGraph:
    def __init__(
        self,
        points: Sequence[PointE],
        p2i: Dict[Tuple[Fraction, Fraction, Fraction, Fraction], int],
        points_f: Optional[Sequence[Tuple[float, float]]] = None,
        share_base: bool = False,
    ):
        if share_base:
            self.points = points  # immutable base geometry; safe to share
            self.point_to_id = p2i
            self.points_f = points_f if points_f is not None else [p.approx() for p in points]
        else:
            self.points = list(points)
            self.point_to_id = dict(p2i)
            self.points_f = list(points_f) if points_f is not None else [p.approx() for p in points]
        self.active_vertices: Set[int] = set()
        self.edges: Set[Tuple[int, int]] = set()
        self.boundary_edges: Set[Tuple[int, int]] = set()
        self.edge_birth: Dict[Tuple[int, int], int] = {}
        self.edge_birth_counter: int = 0
        self.adj: Dict[int, Set[int]] = {}
        self.ray_next: Dict[int, List[Optional[int]]] = {}
        self.ray_dirty: Set[int] = set()
        self.edge_dir_idx: Dict[Tuple[int, int], Optional[int]] = {}
        self.edge_parallel_buckets: List[Set[Tuple[int, int]]] = [set() for _ in range(ANGLE_COUNT // 2)]
        self.edge_unknown_dir: Set[Tuple[int, int]] = set()
        self.incident_dirs_cache: Dict[int, List[int]] = {}
        self.incident_dirs_dirty: Set[int] = set()
        self.kawasaki_cache: Dict[int, float] = {}
        self.kawasaki_dirty: Set[int] = set()

    def _norm_edge(self, i: int, j: int) -> Tuple[int, int]:
        return (i, j) if i < j else (j, i)

    def activate_vertex(self, v: int) -> None:
        self.active_vertices.add(v)
        self.adj.setdefault(v, set())
        if v not in self.ray_next:
            self.ray_next[v] = [None] * ANGLE_COUNT
        self.ray_dirty.add(v)
        self.incident_dirs_dirty.add(v)
        self.kawasaki_dirty.add(v)

    def _mark_local_dirty(self, v: int) -> None:
        self.incident_dirs_dirty.add(v)
        self.kawasaki_dirty.add(v)

    def _edge_dir_bucket(self, i: int, j: int) -> Optional[int]:
        p = self.points[i]
        q = self.points[j]
        d = _exact_dir_idx_from_delta(q.x - p.x, q.y - p.y)
        if d is None:
            return None
        return d % (ANGLE_COUNT // 2)

    def _iter_edges_for_ray_dir(self, dir_idx: int):
        blocked = dir_idx % (ANGLE_COUNT // 2)
        for b, eset in enumerate(self.edge_parallel_buckets):
            if b == blocked:
                continue
            for e in eset:
                yield e
        for e in self.edge_unknown_dir:
            yield e

    def add_vertex(self, p: PointE) -> int:
        key = _point_key(p)
        if key not in self.point_to_id:
            raise ValueError(f"point not found in pre-enumerated grid: {p.approx()}")
        v = self.point_to_id[key]
        self.activate_vertex(v)
        return v

    def add_edge(self, i: int, j: int, boundary: bool = False) -> None:
        if i == j:
            return
        self.activate_vertex(i)
        self.activate_vertex(j)
        e = self._norm_edge(i, j)
        if e in self.edges:
            if boundary:
                self.boundary_edges.add(e)
            return
        pi = self.points_f[i]
        pj = self.points_f[j]
        for u, v in self.edges:
            pu = self.points_f[u]
            pv = self.points_f[v]
            if _collinear_overlap_length(pi, pj, pu, pv) > 1e-10:
                return
        self.edges.add(e)
        self.edge_birth[e] = self.edge_birth_counter
        self.edge_birth_counter += 1
        if boundary:
            self.boundary_edges.add(e)
        self.adj[i].add(j)
        self.adj[j].add(i)
        b = self._edge_dir_bucket(i, j)
        self.edge_dir_idx[e] = b
        if b is None:
            self.edge_unknown_dir.add(e)
        else:
            self.edge_parallel_buckets[b].add(e)
        self._mark_local_dirty(i)
        self._mark_local_dirty(j)

    def remove_edge(self, i: int, j: int) -> None:
        e = self._norm_edge(i, j)
        if e not in self.edges:
            return
        self.edges.remove(e)
        self.boundary_edges.discard(e)
        self.edge_birth.pop(e, None)
        self.adj.get(i, set()).discard(j)
        self.adj.get(j, set()).discard(i)
        b = self.edge_dir_idx.pop(e, None)
        if b is None:
            self.edge_unknown_dir.discard(e)
        else:
            self.edge_parallel_buckets[b].discard(e)
        self._mark_local_dirty(i)
        self._mark_local_dirty(j)

    def init_square_boundary(self) -> Tuple[int, int, int, int]:
        v0 = self.add_vertex(PointE(ZERO, ZERO))
        v1 = self.add_vertex(PointE(ONE, ZERO))
        v2 = self.add_vertex(PointE(ONE, ONE))
        v3 = self.add_vertex(PointE(ZERO, ONE))
        self.add_edge(v0, v1, boundary=True)
        self.add_edge(v1, v2, boundary=True)
        self.add_edge(v2, v3, boundary=True)
        self.add_edge(v3, v0, boundary=True)
        return (v0, v1, v2, v3)

    def recompute_ray_next_for_vertex(self, v: int) -> None:
        self.activate_vertex(v)
        origin = self.points[v]
        row: List[Optional[int]] = [None] * ANGLE_COUNT
        for d in range(ANGLE_COUNT):
            best_t: Optional[Qsqrt2] = None
            best_hit_idx: Optional[int] = None
            for i, j in self._iter_edges_for_ray_dir(d):
                a = self.points[i]
                b = self.points[j]
                hit = _ray_segment_hit(origin, DIRS[d], a, b)
                if hit is None:
                    continue
                t, u, p = hit
                if _q2_cmp(u, ZERO) <= 0:
                    cand = i
                elif _q2_cmp(u, ONE) >= 0:
                    cand = j
                else:
                    key = _point_key(p)
                    cand = self.point_to_id.get(key)
                    if cand is None:
                        continue
                if cand == v:
                    continue
                if best_t is None or _q2_cmp(t, best_t) < 0:
                    best_t = t
                    best_hit_idx = cand
            row[d] = best_hit_idx
        self.ray_next[v] = row
        self.ray_dirty.discard(v)

    def _mark_all_ray_dirty(self) -> None:
        self.ray_dirty.update(self.active_vertices)

    def ensure_ray_next(self, v: int) -> List[Optional[int]]:
        if v not in self.active_vertices:
            self.activate_vertex(v)
        if v in self.ray_dirty:
            self.recompute_ray_next_for_vertex(v)
        return self.ray_next[v]

    def ray_next_at(self, v: int, dir_idx: int) -> Optional[int]:
        return self.ensure_ray_next(v)[dir_idx]

    def recompute_ray_next_all(self) -> None:
        for v in sorted(self.active_vertices):
            self.recompute_ray_next_for_vertex(v)

    def first_hit_edge(self, origin_v: int, dir_idx: int) -> Optional[Tuple[int, int, Qsqrt2, PointE]]:
        origin_f = self.points_f[origin_v]
        d_f = DIRS_F[dir_idx]
        origin = self.points[origin_v]

        # Fast pass: float hit test to shortlist near-best edges.
        best_t_f: Optional[float] = None
        shortlist: List[Tuple[float, int, int]] = []
        tol = 1e-9
        for i, j in self._iter_edges_for_ray_dir(dir_idx):
            hit_f = _ray_segment_hit_float(origin_f, d_f, self.points_f[i], self.points_f[j])
            if hit_f is None:
                continue
            t_f, _ = hit_f
            if best_t_f is None or t_f < best_t_f - tol:
                best_t_f = t_f
                shortlist = [(t_f, i, j)]
            elif abs(t_f - best_t_f) <= tol:
                shortlist.append((t_f, i, j))

        if not shortlist:
            return None

        # Exact pass: choose exact minimum among near-best candidates.
        best_t: Optional[Qsqrt2] = None
        best: Optional[Tuple[int, int, Qsqrt2, PointE]] = None
        shortlist.sort(key=lambda x: x[0])
        for _, i, j in shortlist:
            hit = _ray_segment_hit(origin, DIRS[dir_idx], self.points[i], self.points[j])
            if hit is None:
                continue
            t, u, p = hit
            if best_t is None or _q2_cmp(t, best_t) < 0:
                best_t = t
                best = (i, j, u, p)
        return best

    def shoot_ray_and_split(self, origin_v: int, dir_idx: int) -> Optional[Tuple[int, int]]:
        if origin_v not in self.active_vertices:
            return None
        hit = self.first_hit_edge(origin_v, dir_idx)
        if hit is None:
            return None
        i, j, u, p = hit
        old_e = self._norm_edge(i, j)
        was_boundary = old_e in self.boundary_edges
        if _q2_cmp(u, ZERO) <= 0:
            hit_v = i
        elif _q2_cmp(u, ONE) >= 0:
            hit_v = j
        else:
            key = _point_key(p)
            hit_v = self.point_to_id.get(key)
            if hit_v is None:
                return None
            self.activate_vertex(hit_v)
            self.remove_edge(i, j)
            self.add_edge(i, hit_v, boundary=was_boundary)
            self.add_edge(hit_v, j, boundary=was_boundary)
        self.add_edge(origin_v, hit_v, boundary=False)
        # Edge topology changed; defer recomputation until a vertex row is requested.
        self._mark_all_ray_dirty()
        return (origin_v, hit_v)


def clone_graph(g: GridCreaseGraph) -> GridCreaseGraph:
    h = GridCreaseGraph(
        points=g.points,
        p2i=g.point_to_id,
        points_f=g.points_f,
        share_base=True,
    )
    h.active_vertices = set(g.active_vertices)
    h.edges = set(g.edges)
    h.boundary_edges = set(g.boundary_edges)
    h.edge_birth = dict(g.edge_birth)
    h.edge_birth_counter = g.edge_birth_counter
    h.adj = {k: set(vs) for k, vs in g.adj.items()}
    h.ray_next = {k: list(row) for k, row in g.ray_next.items()}
    h.ray_dirty = set(g.ray_dirty)
    h.edge_dir_idx = dict(g.edge_dir_idx)
    h.edge_parallel_buckets = [set(es) for es in g.edge_parallel_buckets]
    h.edge_unknown_dir = set(g.edge_unknown_dir)
    h.incident_dirs_cache = {k: list(vs) for k, vs in g.incident_dirs_cache.items()}
    h.incident_dirs_dirty = set(g.incident_dirs_dirty)
    h.kawasaki_cache = dict(g.kawasaki_cache)
    h.kawasaki_dirty = set(g.kawasaki_dirty)
    return h


def find_vertex_idx(g: GridCreaseGraph, p: PointE) -> Optional[int]:
    return g.point_to_id.get(_point_key(p))


def _is_boundary_vertex(g: GridCreaseGraph, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    return abs(x) <= tol or abs(x - 1.0) <= tol or abs(y) <= tol or abs(y - 1.0) <= tol


def _on_diag_vertex(g: GridCreaseGraph, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    return abs(x - y) <= tol


def diagonal_symmetry_ok(g: GridCreaseGraph) -> bool:
    for i, j in g.edges:
        mi = find_vertex_idx(g, mirror_point_y_eq_x(g.points[i]))
        mj = find_vertex_idx(g, mirror_point_y_eq_x(g.points[j]))
        if mi is None or mj is None:
            return False
        e = (mi, mj) if mi < mj else (mj, mi)
        if e not in g.edges:
            return False
    return True


def admissible_dirs_for_vertex(g: GridCreaseGraph, v_idx: int, enforce_symmetry: bool) -> List[int]:
    dirs = list(range(ANGLE_COUNT))
    px, py = g.points_f[v_idx]
    start, width = _interior_wedge(px, py, eps=1e-10)
    if width < 2 * pi - 1e-10:
        end = start + width
        dirs = [d for d in dirs if _in_ccw_interval(_angle_of_dir_idx(d), start, end)]

    if enforce_symmetry and _on_diag_vertex(g, v_idx):
        out: List[int] = []
        seen: Set[Tuple[int, int]] = set()
        for d in dirs:
            md = mirrored_dir_idx(d)
            pair = (d, md) if d <= md else (md, d)
            if pair in seen:
                continue
            seen.add(pair)
            if d == md:
                continue
            out.append(min(d, md))
        dirs = out
    return dirs


def _incident_dir_indices(g: GridCreaseGraph, v_idx: int) -> List[int]:
    if v_idx not in g.incident_dirs_dirty:
        cached = g.incident_dirs_cache.get(v_idx)
        if cached is not None:
            return cached
    vp = g.points[v_idx]
    out: Set[int] = set()
    for u in g.adj.get(v_idx, set()):
        up = g.points[u]
        d = _exact_dir_idx_from_delta(up.x - vp.x, up.y - vp.y)
        if d is None:
            ux, uy = g.points_f[u]
            vx, vy = g.points_f[v_idx]
            d = _nearest_dir_idx(ux - vx, uy - vy)
        out.add(d)
    result = sorted(out)
    g.incident_dirs_cache[v_idx] = result
    g.incident_dirs_dirty.discard(v_idx)
    return result


def _sector_steps_cyclic(sorted_dirs: Sequence[int]) -> List[int]:
    if not sorted_dirs:
        return []
    out: List[int] = []
    n = len(sorted_dirs)
    for i in range(n):
        a = sorted_dirs[i]
        b = sorted_dirs[(i + 1) % n]
        out.append((b - a) % ANGLE_COUNT)
    return out


def _kawasaki_residual_from_dirs(sorted_dirs: Sequence[int]) -> float:
    n = len(sorted_dirs)
    if n < 4 or n % 2 != 0:
        return float("inf")
    sec_steps = _sector_steps_cyclic(sorted_dirs)
    target = ANGLE_COUNT // 2
    odd_steps = sum(sec_steps[::2])
    even_steps = sum(sec_steps[1::2])
    return float(abs(odd_steps - target) + abs(even_steps - target)) * (pi / 8.0)


def vertex_kawasaki_error(g: GridCreaseGraph, v_idx: int) -> float:
    if v_idx not in g.kawasaki_dirty:
        cached = g.kawasaki_cache.get(v_idx)
        if cached is not None:
            return cached
    ke = _kawasaki_residual_from_dirs(_incident_dir_indices(g, v_idx))
    g.kawasaki_cache[v_idx] = ke
    g.kawasaki_dirty.discard(v_idx)
    return ke


def _kawasaki_target_vertex_ids(g: GridCreaseGraph) -> List[int]:
    return [v for v in sorted(g.active_vertices) if not _is_boundary_vertex(g, v)]


def _repair_open_sink_vertices(
    base: GridCreaseGraph,
    g: GridCreaseGraph,
    enforce_symmetry: bool,
    max_bounces: int,
    tol: float = 1e-8,
    max_rounds: int = 2,
) -> GridCreaseGraph:
    h = clone_graph(g)
    for _ in range(max_rounds):
        targets = [v for v in _kawasaki_target_vertex_ids(h) if vertex_kawasaki_error(h, v) > tol]
        if not targets:
            return h
        progressed = False
        for v in targets:
            before_ke = vertex_kawasaki_error(h, v)
            before_total = sum(vertex_kawasaki_error(h, u) for u in _kawasaki_target_vertex_ids(h))
            used = set(_incident_dir_indices(h, v))
            admissible = admissible_dirs_for_vertex(h, v, enforce_symmetry=enforce_symmetry)
            cand = _symmetric_candidate_dirs(used, admissible, incoming_d=None)
            if not cand:
                cand = [d for d in admissible if d not in used]
            if not cand:
                continue
            cand = sorted(
                cand,
                key=lambda d: _kawasaki_residual_from_dirs(sorted(set(used | {d}))),
            )[:2]
            best_h: Optional[GridCreaseGraph] = None
            best_key: Optional[Tuple[float, float]] = None
            for d in cand:
                hh = apply_open_sink_action(
                    h,
                    v_idx=v,
                    dir_idx=d,
                    enforce_symmetry=enforce_symmetry,
                    max_bounces=max_bounces,
                    enable_repair=False,
                )
                if hh is None:
                    continue
                after_ke = vertex_kawasaki_error(hh, v)
                after_total = sum(vertex_kawasaki_error(hh, u) for u in _kawasaki_target_vertex_ids(hh))
                key = (after_ke, after_total)
                if best_key is None or key < best_key:
                    best_key = key
                    best_h = hh
            if best_h is None or best_key is None:
                continue
            if best_key[0] < before_ke - 1e-12 or best_key[1] < before_total - 1e-12:
                h = best_h
                progressed = True
                break
        if not progressed:
            break
    return h


def _repair_priority_corners_open_sink(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    enforce_symmetry: bool,
    max_bounces: int,
    tol: float = 1e-8,
    max_rounds: int = 2,
    max_try_dirs: int = 4,
) -> GridCreaseGraph:
    h = clone_graph(g)
    cset = [v for v in corner_ids if v in h.active_vertices and (not _is_boundary_vertex(h, v))]
    if not cset:
        return h
    for _ in range(max_rounds):
        targets = [v for v in cset if vertex_kawasaki_error(h, v) > tol]
        if not targets:
            return h
        progressed = False
        # Repair corners with larger violation first.
        targets.sort(key=lambda v: vertex_kawasaki_error(h, v), reverse=True)
        for v in targets:
            before_ke = vertex_kawasaki_error(h, v)
            used = set(_incident_dir_indices(h, v))
            admissible = admissible_dirs_for_vertex(h, v, enforce_symmetry=enforce_symmetry)
            cand = [d for d in admissible if d not in used]
            if not cand:
                continue
            cand = sorted(
                cand,
                key=lambda d: _kawasaki_residual_from_dirs(sorted(set(used | {d}))),
            )[:max_try_dirs]
            best_h: Optional[GridCreaseGraph] = None
            best_key: Optional[Tuple[float, float]] = None
            for d in cand:
                hh = apply_open_sink_action(
                    h,
                    v_idx=v,
                    dir_idx=d,
                    enforce_symmetry=enforce_symmetry,
                    max_bounces=max_bounces,
                    enable_repair=False,
                )
                if hh is None:
                    continue
                after_ke = vertex_kawasaki_error(hh, v)
                # Also prefer reducing total corner Kawasaki residual.
                after_total_corner = sum(vertex_kawasaki_error(hh, u) for u in cset)
                key = (after_ke, after_total_corner)
                if best_key is None or key < best_key:
                    best_key = key
                    best_h = hh
            if best_h is None or best_key is None:
                continue
            if best_key[0] < before_ke - 1e-12:
                h = best_h
                progressed = True
                break
        if not progressed:
            break
    return h


def apply_ray_action(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool = True,
) -> Optional[GridCreaseGraph]:
    h = clone_graph(g)
    if h.shoot_ray_and_split(v_idx, dir_idx) is None:
        return None
    if enforce_symmetry:
        mv = find_vertex_idx(h, mirror_point_y_eq_x(g.points[v_idx]))
        if mv is None:
            return None
        md = mirrored_dir_idx(dir_idx)
        if not (mv == v_idx and md == dir_idx):
            if h.shoot_ray_and_split(mv, md) is None:
                return None
        if not diagonal_symmetry_ok(h):
            return None
    return h


def _run_open_sink_transaction(
    g: GridCreaseGraph,
    fronts_init: Sequence[Tuple[int, int]],
    enforce_symmetry: bool = True,
    max_bounces: int = 14,
) -> Optional[GridCreaseGraph]:
    if not fronts_init:
        return None
    h = clone_graph(g)
    ray_vs = [v for v, _ in fronts_init]
    ray_ds = [d for _, d in fronts_init]
    ray_done = [False] * len(fronts_init)
    config_seen: Set[Tuple[Tuple[int, int], ...]] = set()

    def _dir_gap(a: int, b: int) -> int:
        d = abs(a - b) % ANGLE_COUNT
        return min(d, ANGLE_COUNT - d)

    def _next_dir_at_existing_vertex(v_idx: int, incoming_d: int) -> Optional[int]:
        used = set(_incident_dir_indices(h, v_idx))
        admissible = admissible_dirs_for_vertex(h, v_idx, enforce_symmetry=False)
        cand = _symmetric_candidate_dirs(used, admissible, incoming_d=incoming_d)
        if not cand:
            # Fallback when strict symmetric candidates are unavailable.
            cand = [d for d in admissible if d not in used]
        if not cand:
            return None
        scored: List[Tuple[int, float, int, int]] = []
        for d in cand:
            local = sorted(set(used | {d}))
            ke = _kawasaki_residual_from_dirs(local)
            sat = 0 if ke <= 1e-8 else 1
            scored.append((sat, ke, _dir_gap(d, incoming_d), d))
        scored.sort()
        return scored[0][3]

    def _config() -> Tuple[Tuple[int, int], ...]:
        cur: List[Tuple[int, int]] = []
        for i in range(len(ray_vs)):
            cur.append((ray_vs[i], -1 if ray_done[i] else ray_ds[i]))
        cur.sort()
        return tuple(cur)

    config_seen.add(_config())
    for _ in range(max_bounces):
        for rid in range(len(ray_vs)):
            if ray_done[rid]:
                continue
            cur_v = ray_vs[rid]
            cur_d = ray_ds[rid]
            hit = h.first_hit_edge(cur_v, cur_d)
            if hit is None:
                return None
            i, j, u, p_hit = hit
            a_f = h.points_f[i]
            b_f = h.points_f[j]
            hit_interior = _q2_cmp(u, ZERO) > 0 and _q2_cmp(u, ONE) < 0
            if h.shoot_ray_and_split(cur_v, cur_d) is None:
                return None

            if _q2_cmp(u, ZERO) <= 0:
                next_v = i
            elif _q2_cmp(u, ONE) >= 0:
                next_v = j
            else:
                next_v = find_vertex_idx(h, p_hit)
            if next_v is None:
                return None
            ray_vs[rid] = next_v

            if _on_diag_vertex(h, next_v):
                ray_done[rid] = True
                continue
            if _is_boundary_vertex(h, next_v):
                ray_done[rid] = True
                continue

            if hit_interior:
                ray_ds[rid] = _reflected_dir_idx(cur_d, a_f, b_f)
            else:
                nd = _next_dir_at_existing_vertex(next_v, cur_d)
                if nd is None:
                    return None
                ray_ds[rid] = nd

        active = [ray_vs[i] for i in range(len(ray_vs)) if not ray_done[i]]
        if len(active) != len(set(active)) or all(ray_done):
            break
        c = _config()
        if c in config_seen:
            break
        config_seen.add(c)

    if enforce_symmetry and not diagonal_symmetry_ok(h):
        return None
    return h


def apply_open_sink_action(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool = True,
    max_bounces: int = 14,
    enable_repair: bool = True,
) -> Optional[GridCreaseGraph]:
    h0 = clone_graph(g)
    fronts: List[Tuple[int, int]] = [(v_idx, dir_idx)]
    if enforce_symmetry:
        mv = find_vertex_idx(h0, mirror_point_y_eq_x(h0.points[v_idx]))
        if mv is None:
            return None
        fronts.append((mv, mirrored_dir_idx(dir_idx)))
    uniq: List[Tuple[int, int]] = []
    seen: Set[Tuple[int, int]] = set()
    for f in fronts:
        if f in seen:
            continue
        seen.add(f)
        uniq.append(f)
    out = _run_open_sink_transaction(
        h0,
        fronts_init=uniq,
        enforce_symmetry=enforce_symmetry,
        max_bounces=max_bounces,
    )
    if out is None:
        return None
    if enable_repair:
        out = _repair_open_sink_vertices(
            g,
            out,
            enforce_symmetry=enforce_symmetry,
            max_bounces=max_bounces,
        )
        if enforce_symmetry and not diagonal_symmetry_ok(out):
            return None
    return out


def _is_point_on_line(a: Tuple[float, float], b: Tuple[float, float], p: Tuple[float, float], tol: float = 1e-8) -> bool:
    abx, aby = b[0] - a[0], b[1] - a[1]
    apx, apy = p[0] - a[0], p[1] - a[1]
    return abs(_cross_f(abx, aby, apx, apy)) <= tol


def _add_segment_with_splits_ids(
    g: GridCreaseGraph,
    start_v: int,
    goal_v: int,
    max_steps: int = 32,
) -> bool:
    if start_v == goal_v:
        return False
    p0 = g.points[start_v]
    p1 = g.points[goal_v]
    d0 = _exact_dir_idx_from_delta(p1.x - p0.x, p1.y - p0.y)
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
        hit = g.shoot_ray_and_split(cur, d0)
        if hit is None:
            return False
        _, nxt = hit
        if nxt == cur:
            return False
        if not _is_point_on_line(a, b, g.points_f[nxt], tol=1e-7):
            return False
        changed = True
        cur = nxt
        if cur in seen:
            return False
        seen.add(cur)
    return False


def apply_triangle_macro_variants(
    g: GridCreaseGraph,
    anchor_v: int,
    enforce_symmetry: bool = True,
    max_other_vertices: int = 6,
    max_centers: int = 3,
) -> List[GridCreaseGraph]:
    ax, ay = g.points_f[anchor_v]
    if enforce_symmetry and ax > ay + 1e-10:
        return []

    others = [v for v in g.active_vertices if v != anchor_v]
    others.sort(key=lambda v: (g.points_f[v][0] - ax) ** 2 + (g.points_f[v][1] - ay) ** 2)
    others = others[:max_other_vertices]

    out: List[GridCreaseGraph] = []
    seen: Set[Tuple] = set()
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
                    if _exact_dir_idx_from_delta(q.x - p.x, q.y - p.y) is None:
                        ok = False
                        break
                if not ok:
                    continue
                h = clone_graph(g)
                changed = False
                for sv in trip:
                    changed = _add_segment_with_splits_ids(h, sv, c) or changed
                if enforce_symmetry:
                    mc = find_vertex_idx(h, mirror_point_y_eq_x(h.points[c]))
                    if mc is None:
                        continue
                    for sv in trip:
                        msv = find_vertex_idx(h, mirror_point_y_eq_x(h.points[sv]))
                        if msv is None:
                            changed = False
                            break
                        changed = _add_segment_with_splits_ids(h, msv, mc) or changed
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


def _exact_dir_idx_from_delta(dx: Qsqrt2, dy: Qsqrt2) -> Optional[int]:
    for k, (rx, ry) in enumerate(DIRS):
        c = _cross(dx, dy, rx, ry)
        if c != ZERO:
            continue
        d = _dot(dx, dy, rx, ry)
        s = _q2_sign(d)
        if s > 0:
            return k
        if s < 0:
            return (k + ANGLE_COUNT // 2) % ANGLE_COUNT
    return None


def _is_aligned_with_16_dirs(p: PointE, q: PointE) -> bool:
    dx = q.x - p.x
    dy = q.y - p.y
    if dx == ZERO and dy == ZERO:
        return False
    for rx, ry in DIRS:
        if _cross(dx, dy, rx, ry) == ZERO:
            return True
    return False


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


def _crosses_existing_edges(g: GridCreaseGraph, i: int, j: int) -> bool:
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


def seed_direct_corner_connections(g: GridCreaseGraph, corner_ids: Sequence[int]) -> None:
    ids = list(corner_ids)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            u = ids[i]
            v = ids[j]
            e = (u, v) if u < v else (v, u)
            if e in g.edges:
                continue
            p = g.points[u]
            q = g.points[v]
            if not _is_aligned_with_16_dirs(p, q):
                continue
            if _crosses_existing_edges(g, u, v):
                continue
            g.add_edge(u, v, boundary=False)


def used_dir_indices(g: GridCreaseGraph, v_idx: int, include_boundary: bool = False) -> Set[int]:
    out: Set[int] = set()
    for u in g.adj.get(v_idx, set()):
        e = (v_idx, u) if v_idx < u else (u, v_idx)
        if not include_boundary and e in g.boundary_edges:
            continue
        p = g.points[v_idx]
        q = g.points[u]
        d = _exact_dir_idx_from_delta(q.x - p.x, q.y - p.y)
        if d is not None:
            out.add(d)
    return out


def incident_angles(g: GridCreaseGraph, v_idx: int, include_boundary: bool = False) -> List[float]:
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


def corner_sectors(g: GridCreaseGraph, v_idx: int) -> List[float]:
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


def corner_condition_error(g: GridCreaseGraph, v_idx: int, max_deg: float) -> float:
    thr = max_deg * pi / 180.0
    secs = corner_sectors(g, v_idx)
    return sum(max(0.0, s - thr) for s in secs)


def corner_line_count(g: GridCreaseGraph, v_idx: int) -> int:
    cnt = 0
    for u in g.adj.get(v_idx, set()):
        e = (v_idx, u) if v_idx < u else (u, v_idx)
        if e in g.boundary_edges:
            continue
        cnt += 1
    return cnt


def corner_score(
    g: GridCreaseGraph,
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


def kawasaki_score(
    g: GridCreaseGraph,
    tol: float = 1e-8,
) -> Tuple[int, float, int]:
    targets = _kawasaki_target_vertex_ids(g)
    bad = 0
    total = 0.0
    for v in targets:
        ke = vertex_kawasaki_error(g, v)
        val = 1000.0 if ke == float("inf") else ke
        total += val
        if val > tol:
            bad += 1
    return (bad, total, len(targets))


def global_score(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int = 2,
    kawasaki_tol: float = 1e-8,
) -> Tuple[int, int, int, float, float, float]:
    bad_corner, lowdeg, total_corner, lowdeg_pen = corner_score(
        g,
        corner_ids=corner_ids,
        max_deg=max_deg,
        min_corner_lines=min_corner_lines,
    )
    bad_k, total_k, _ = kawasaki_score(g, tol=kawasaki_tol)
    # Prioritize global Kawasaki satisfaction first, then corner metrics.
    return (bad_k, bad_corner, lowdeg, total_k, total_corner, lowdeg_pen)


def priority_corner_kawasaki_score(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    tol: float = 1e-8,
) -> Tuple[int, float]:
    bad = 0
    total = 0.0
    for v in corner_ids:
        if v not in g.active_vertices:
            continue
        if _is_boundary_vertex(g, v):
            continue
        ke = vertex_kawasaki_error(g, v)
        val = 1000.0 if ke == float("inf") else ke
        total += val
        if val > tol:
            bad += 1
    return (bad, total)


def violating_vertex_priority(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int,
    kawasaki_tol: float,
) -> List[int]:
    cset = set(corner_ids)
    cand: Set[int] = set()
    for v in corner_ids:
        if corner_condition_error(g, v, max_deg=max_deg) > 1e-12:
            cand.add(v)
        if corner_line_count(g, v) < min_corner_lines:
            cand.add(v)
    for v in _kawasaki_target_vertex_ids(g):
        if vertex_kawasaki_error(g, v) > kawasaki_tol:
            cand.add(v)
    return sorted(
        list(cand),
        key=lambda v: (
            0 if v not in cset else 1,
            -vertex_kawasaki_error(g, v),
            -corner_condition_error(g, v, max_deg=max_deg),
            -(max(0, min_corner_lines - corner_line_count(g, v))),
        ),
    )


def graph_state_key(g: GridCreaseGraph) -> Tuple:
    pts = g.points
    keys = []
    for i, j in g.edges:
        a = _point_key(pts[i])
        b = _point_key(pts[j])
        keys.append((a, b) if a <= b else (b, a))
    keys.sort()
    return tuple(keys)


def dfs_repair_corners(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    max_deg: float = 45.0,
    max_depth: int = 24,
    branch_per_node: int = 14,
    allow_violations: int = 2,
    max_nodes: int = 4000,
    enforce_symmetry: bool = True,
    enable_open_sink: bool = True,
    open_sink_max_bounces: int = 14,
    min_corner_lines: int = 2,
    kawasaki_tol: float = 1e-8,
    enable_corner_kawasaki_repair: bool = True,
    enable_triangle_macro: bool = False,
    require_corner_kawasaki: bool = True,
    search_stats: Optional[Dict[str, int]] = None,
) -> GridCreaseGraph:
    stats = search_stats if search_stats is not None else {}

    def _inc(key: str, n: int = 1) -> None:
        stats[key] = stats.get(key, 0) + n

    best = clone_graph(g)
    best_score = global_score(
        best,
        corner_ids=corner_ids,
        max_deg=max_deg,
        min_corner_lines=min_corner_lines,
        kawasaki_tol=kawasaki_tol,
    )
    seen: Set[Tuple] = {graph_state_key(g)}
    node_counter = 0
    solved = False

    def recurse(state: GridCreaseGraph, depth: int) -> None:
        nonlocal best, best_score, node_counter, solved
        _inc("recurse_calls")
        if solved:
            _inc("prune_already_solved")
            return
        node_counter += 1
        _inc("visited_nodes")
        if node_counter > max_nodes:
            _inc("prune_max_nodes")
            return
        sc = global_score(
            state,
            corner_ids=corner_ids,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        if sc < best_score:
            best = clone_graph(state)
            best_score = sc
        ck = priority_corner_kawasaki_score(state, corner_ids=corner_ids, tol=kawasaki_tol)
        if sc[0] == 0 and sc[1] == 0 and sc[2] == 0 and (ck[0] == 0 or not require_corner_kawasaki):
            solved = True
            _inc("solved_nodes")
            best = clone_graph(state)
            best_score = sc
            return
        if (sc[0] == 0 and sc[1] <= allow_violations and sc[2] == 0) or depth >= max_depth:
            if depth >= max_depth:
                _inc("prune_max_depth")
            else:
                _inc("prune_allow_violations")
            return

        priority = violating_vertex_priority(
            state,
            corner_ids=corner_ids,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        child_pool: List[Tuple[Tuple[int, int, int, float, float, float], GridCreaseGraph]] = []
        for v in priority[:6]:
            used = used_dir_indices(state, v, include_boundary=False)
            for d in admissible_dirs_for_vertex(state, v, enforce_symmetry=enforce_symmetry):
                _inc("candidate_dirs_total")
                if d in used:
                    _inc("reject_used_dir")
                    continue
                if state.ray_next_at(v, d) is None:
                    _inc("reject_no_ray_hit")
                    continue
                if enable_open_sink:
                    h = apply_open_sink_action(
                        state,
                        v_idx=v,
                        dir_idx=d,
                        enforce_symmetry=enforce_symmetry,
                        max_bounces=open_sink_max_bounces,
                    )
                    if h is None:
                        _inc("reject_action_failed")
                        continue
                    if enable_corner_kawasaki_repair:
                        h = _repair_priority_corners_open_sink(
                            h,
                            corner_ids=corner_ids,
                            enforce_symmetry=enforce_symmetry,
                            max_bounces=open_sink_max_bounces,
                            tol=kawasaki_tol,
                        )
                else:
                    h = apply_ray_action(state, v_idx=v, dir_idx=d, enforce_symmetry=enforce_symmetry)
                    if h is None:
                        _inc("reject_action_failed")
                        continue
                k = graph_state_key(h)
                if k in seen:
                    _inc("reject_seen_state")
                    continue
                seen.add(k)
                hsc = global_score(
                    h,
                    corner_ids=corner_ids,
                    max_deg=max_deg,
                    min_corner_lines=min_corner_lines,
                    kawasaki_tol=kawasaki_tol,
                )
                if hsc[0] > sc[0] + 2:
                    _inc("reject_score_bad_kawasaki")
                    continue
                if hsc[1] > sc[1] + 2:
                    _inc("reject_score_bad_corner")
                    continue
                if hsc[2] > sc[2] + 2:
                    _inc("reject_score_bad_lowline")
                    continue
                if require_corner_kawasaki:
                    hck = priority_corner_kawasaki_score(h, corner_ids=corner_ids, tol=kawasaki_tol)
                    # Do not allow worsening on priority-corner Kawasaki violations.
                    if hck[0] > ck[0]:
                        _inc("reject_priority_corner_kawasaki")
                        continue
                _inc("accepted_children")
                child_pool.append((hsc, h))
        child_pool.sort(key=lambda x: x[0])
        if len(child_pool) > branch_per_node:
            _inc("prune_branch_limit", len(child_pool) - branch_per_node)
        for _, h in child_pool[:branch_per_node]:
            recurse(h, depth + 1)

        if enable_triangle_macro and (not solved) and depth < max_depth:
            tri_children: List[Tuple[Tuple[int, int, int, float, float, float], GridCreaseGraph]] = []
            for v in priority[:3]:
                for h in apply_triangle_macro_variants(
                    state,
                    anchor_v=v,
                    enforce_symmetry=enforce_symmetry,
                    max_other_vertices=6,
                    max_centers=3,
                ):
                    k = graph_state_key(h)
                    if k in seen:
                        continue
                    seen.add(k)
                    hsc = global_score(
                        h,
                        corner_ids=corner_ids,
                        max_deg=max_deg,
                        min_corner_lines=min_corner_lines,
                        kawasaki_tol=kawasaki_tol,
                    )
                    if require_corner_kawasaki:
                        hck = priority_corner_kawasaki_score(h, corner_ids=corner_ids, tol=kawasaki_tol)
                        if hck[0] > ck[0]:
                            continue
                    tri_children.append((hsc, h))
            tri_children.sort(key=lambda x: x[0])
            for _, h in tri_children[:max(1, branch_per_node // 2)]:
                recurse(h, depth + 1)

    recurse(g, 0)
    return best


def make_grid_graph(
    corners: Sequence[PointE],
    a_max: int,
    b_max: int,
    k_max: int,
) -> Tuple[GridCreaseGraph, List[int]]:
    points, p2i = enumerate_grid_points(a_max=a_max, b_max=b_max, k_max=k_max)
    g = GridCreaseGraph(points=points, p2i=p2i)
    g.init_square_boundary()
    # Seed the main diagonal y=x as in generator_exact.
    v00 = g.add_vertex(PointE(ZERO, ZERO))
    v11 = g.add_vertex(PointE(ONE, ONE))
    g.add_edge(v00, v11, boundary=False)
    corner_ids = [g.add_vertex(p) for p in corners]
    # Seed direct corner-to-corner connections on the 16-direction grid.
    seed_direct_corner_connections(g, corner_ids)
    g.recompute_ray_next_all()
    return g, corner_ids


def graph_stats(g: GridCreaseGraph) -> Dict[str, int]:
    max_k = -1
    for v in g.active_vertices:
        p = g.points[v]
        k = _point_k_level(p)
        if k is not None:
            max_k = max(max_k, k)
    return {
        "grid_points_total": len(g.points),
        "active_vertices": len(g.active_vertices),
        "edges": len(g.edges),
        "max_k_active": max_k,
    }


def remap_graph_to_new_grid(src: GridCreaseGraph, dst: GridCreaseGraph) -> None:
    vmap: Dict[int, int] = {}
    for v in src.active_vertices:
        key = _point_key(src.points[v])
        nv = dst.point_to_id.get(key)
        if nv is None:
            continue
        dst.activate_vertex(nv)
        vmap[v] = nv
    for i, j in src.edges:
        ni = vmap.get(i)
        nj = vmap.get(j)
        if ni is None or nj is None or ni == nj:
            continue
        e = (i, j) if i < j else (j, i)
        dst.add_edge(ni, nj, boundary=(e in src.boundary_edges))
    dst._mark_all_ray_dirty()


def lattice_bounds_active(g: GridCreaseGraph) -> Dict[str, int]:
    max_k = -1
    max_abs_a = 0
    max_abs_b = 0
    for v in g.active_vertices:
        p = g.points[v]
        for z in (p.x, p.y):
            ka = _v2_of_denominator(z.a)
            kb = _v2_of_denominator(z.b)
            if ka is None or kb is None:
                continue
            k = max(ka, kb)
            max_k = max(max_k, k)
            aa = z.a * (2**k)
            bb = z.b * (2**k)
            max_abs_a = max(max_abs_a, abs(aa.numerator))
            max_abs_b = max(max_abs_b, abs(bb.numerator))
    return {"max_k": max_k, "max_abs_a": max_abs_a, "max_abs_b": max_abs_b}


def render_pattern(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    out_path: str = "_tmp_out/grid_pattern.png",
    show_order: bool = False,
) -> None:
    import matplotlib.pyplot as plt

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

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.2)
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def _parse_qsqrt2_token(tok: str) -> Qsqrt2:
    t = tok.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("empty token")
    if t in ("sqrt2", "sqrt(2)"):
        return Qsqrt2(Fraction(0), Fraction(1))
    if t in ("1/sqrt2", "1/sqrt(2)", "sqrt2/2", "sqrt(2)/2"):
        return INV_SQRT2
    if "sqrt2" in t or "sqrt(2)" in t:
        t = t.replace("sqrt(2)", "sqrt2")
        sign = 1
        if t.startswith("-"):
            sign = -1
            t = t[1:]
        if t == "sqrt2":
            return Qsqrt2(Fraction(0), Fraction(sign))
        if t.endswith("*sqrt2"):
            c = Fraction(t[:-6])
            return Qsqrt2(Fraction(0), sign * c)
        if t.startswith("sqrt2/"):
            d = Fraction(1, int(t.split("/")[1]))
            return Qsqrt2(Fraction(0), sign * d)
        raise ValueError(f"unsupported sqrt2 token: {tok}")
    return Qsqrt2(Fraction(t), Fraction(0))


def parse_corners(text: str) -> List[PointE]:
    pts: List[PointE] = []
    chunks = [c.strip() for c in text.split(";") if c.strip()]
    if not chunks:
        raise ValueError("corners is empty")
    for c in chunks:
        c = c.strip()
        if c.startswith("(") and c.endswith(")"):
            c = c[1:-1].strip()
        xy = [x.strip() for x in c.split(",")]
        if len(xy) != 2:
            raise ValueError(f"invalid corner format: {c}")
        p = PointE(_parse_qsqrt2_token(xy[0]), _parse_qsqrt2_token(xy[1]))
        if not _in_square(p):
            raise ValueError(f"corner out of [0,1]^2: {c}")
        pts.append(p)
    return pts


def corners_diag_symmetric(corners: Sequence[PointE]) -> bool:
    s = {_point_key(p) for p in corners}
    for p in corners:
        if _point_key(mirror_point_y_eq_x(p)) not in s:
            return False
    return True


def run(
    corners: Sequence[PointE],
    a_max: int = 8,
    b_max: int = 8,
    k_max: int = 3,
    corner_max_deg: float = 45.0,
    max_depth: int = 6,
    branch_per_node: int = 4,
    allow_violations: int = 2,
    max_nodes: int = 300,
    enforce_symmetry: bool = True,
    enable_open_sink: bool = True,
    open_sink_max_bounces: int = 14,
    min_corner_lines: int = 2,
    kawasaki_tol: float = 1e-8,
    enable_corner_kawasaki_repair: bool = True,
    enable_triangle_macro: bool = False,
    require_corner_kawasaki: bool = True,
    staged_k_relax: bool = False,
    k_start: int = 1,
    show_order: bool = False,
    render_image: bool = True,
    out_path: str = "_tmp_out/grid_pattern.png",
) -> Dict[str, object]:
    if enforce_symmetry and not corners_diag_symmetric(corners):
        raise ValueError("enforce_symmetry=True requires corners to be y=x symmetric")
    t0 = time.perf_counter()
    stage_logs: List[Dict[str, object]] = []
    search_stats: Dict[str, int] = {}
    if staged_k_relax:
        ks = max(1, min(k_start, k_max))
    else:
        ks = k_max

    g, corner_ids = make_grid_graph(corners, a_max=a_max, b_max=b_max, k_max=ks)
    before = corner_score(g, corner_ids=corner_ids, max_deg=corner_max_deg, min_corner_lines=min_corner_lines)
    before_k = kawasaki_score(g, tol=kawasaki_tol)
    before_ck = priority_corner_kawasaki_score(g, corner_ids=corner_ids, tol=kawasaki_tol)

    best = clone_graph(g)
    if staged_k_relax:
        for kcur in range(ks, k_max + 1):
            if kcur > ks:
                ng, ncorner_ids = make_grid_graph(corners, a_max=a_max, b_max=b_max, k_max=kcur)
                remap_graph_to_new_grid(best, ng)
                g = ng
                corner_ids = ncorner_ids
            best = dfs_repair_corners(
                g,
                corner_ids=corner_ids,
                max_deg=corner_max_deg,
                max_depth=max_depth,
                branch_per_node=branch_per_node,
                allow_violations=allow_violations,
                max_nodes=max_nodes,
                enforce_symmetry=enforce_symmetry,
                enable_open_sink=enable_open_sink,
                open_sink_max_bounces=open_sink_max_bounces,
                min_corner_lines=min_corner_lines,
                kawasaki_tol=kawasaki_tol,
                enable_corner_kawasaki_repair=enable_corner_kawasaki_repair,
                enable_triangle_macro=enable_triangle_macro,
                require_corner_kawasaki=require_corner_kawasaki,
                search_stats=search_stats,
            )
            g = best
            stage_logs.append(
                {
                    "k": kcur,
                    "corner_score": corner_score(best, corner_ids=corner_ids, max_deg=corner_max_deg, min_corner_lines=min_corner_lines),
                    "kawasaki_score": kawasaki_score(best, tol=kawasaki_tol),
                    "stats": graph_stats(best),
                }
            )
    else:
        best = dfs_repair_corners(
            g,
            corner_ids=corner_ids,
            max_deg=corner_max_deg,
            max_depth=max_depth,
            branch_per_node=branch_per_node,
            allow_violations=allow_violations,
            max_nodes=max_nodes,
            enforce_symmetry=enforce_symmetry,
            enable_open_sink=enable_open_sink,
            open_sink_max_bounces=open_sink_max_bounces,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
            enable_corner_kawasaki_repair=enable_corner_kawasaki_repair,
            enable_triangle_macro=enable_triangle_macro,
            require_corner_kawasaki=require_corner_kawasaki,
            search_stats=search_stats,
        )
    after = corner_score(best, corner_ids=corner_ids, max_deg=corner_max_deg, min_corner_lines=min_corner_lines)
    after_k = kawasaki_score(best, tol=kawasaki_tol)
    after_ck = priority_corner_kawasaki_score(best, corner_ids=corner_ids, tol=kawasaki_tol)
    corner_errs = [corner_condition_error(best, v, max_deg=corner_max_deg) for v in corner_ids]
    corner_line_counts = [corner_line_count(best, v) for v in corner_ids]
    if render_image:
        render_pattern(best, corner_ids=corner_ids, out_path=out_path, show_order=show_order)
    elapsed = time.perf_counter() - t0
    result: Dict[str, object] = {
        "sec": round(elapsed, 3),
        "params": {
            "a_max": a_max,
            "b_max": b_max,
            "k_max": k_max,
            "corner_max_deg": corner_max_deg,
            "max_depth": max_depth,
            "branch_per_node": branch_per_node,
            "allow_violations": allow_violations,
            "max_nodes": max_nodes,
            "enforce_symmetry": enforce_symmetry,
            "enable_open_sink": enable_open_sink,
            "open_sink_max_bounces": open_sink_max_bounces,
            "min_corner_lines": min_corner_lines,
            "kawasaki_tol": kawasaki_tol,
            "enable_corner_kawasaki_repair": enable_corner_kawasaki_repair,
            "enable_triangle_macro": enable_triangle_macro,
            "require_corner_kawasaki": require_corner_kawasaki,
            "staged_k_relax": staged_k_relax,
            "k_start": k_start,
            "show_order": show_order,
        },
        "stats_before": graph_stats(g),
        "stats_after": graph_stats(best),
        "lattice_bounds_after": lattice_bounds_active(best),
        "corner_score_before": before,
        "corner_score_after": after,
        "kawasaki_score_before": before_k,
        "kawasaki_score_after": after_k,
        "priority_corner_kawasaki_before": before_ck,
        "priority_corner_kawasaki_after": after_ck,
        "corner_errors_after": corner_errs,
        "corner_line_counts_after": corner_line_counts,
        "corner_lowline_after": sum(1 for c in corner_line_counts if c < min_corner_lines),
        "corner_violations_after": sum(1 for e in corner_errs if e > 1e-12),
        "kawasaki_violations_after": after_k[0],
        "priority_corner_kawasaki_violations_after": after_ck[0],
        "search_stats": search_stats,
        "stage_logs": stage_logs if staged_k_relax else None,
        "out_path": out_path if render_image else None,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid-based origami crease generator (standalone).")
    parser.add_argument(
        "--corners",
        type=str,
        default="(0,0);(1,1);(0,1);(1,0);(1/sqrt2,0);(1,1/sqrt2);(0,1/sqrt2);(1/sqrt2,1);(1/2,1/2)",
        help="Semicolon-separated corners, e.g. '(0,0);(1,0);(1/sqrt2,1/sqrt2)'",
    )
    parser.add_argument("--a-max", type=int, default=8)
    parser.add_argument("--b-max", type=int, default=8)
    parser.add_argument("--k-max", type=int, default=3)
    parser.add_argument("--corner-max-deg", type=float, default=45.0)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--branch-per-node", type=int, default=4)
    parser.add_argument("--allow-violations", type=int, default=2)
    parser.add_argument("--max-nodes", type=int, default=300)
    parser.add_argument("--max-bounces", type=int, default=14)
    parser.add_argument("--min-corner-lines", type=int, default=2)
    parser.add_argument("--kawasaki-tol", type=float, default=1e-8)
    parser.add_argument("--no-corner-kawasaki-repair", action="store_true")
    parser.add_argument("--triangle-macro", action="store_true")
    parser.add_argument("--no-require-corner-kawasaki", action="store_true")
    parser.add_argument("--staged-k-relax", action="store_true")
    parser.add_argument("--k-start", type=int, default=1)
    parser.add_argument("--show-order", action="store_true")
    parser.add_argument("--no-symmetry", action="store_true")
    parser.add_argument("--no-open-sink", action="store_true")
    parser.add_argument("--out-path", type=str, default="_tmp_out/grid_pattern.png")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()

    corners = parse_corners(args.corners)
    result = run(
        corners=corners,
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
        open_sink_max_bounces=args.max_bounces,
        min_corner_lines=args.min_corner_lines,
        kawasaki_tol=args.kawasaki_tol,
        enable_corner_kawasaki_repair=not args.no_corner_kawasaki_repair,
        enable_triangle_macro=args.triangle_macro,
        require_corner_kawasaki=not args.no_require_corner_kawasaki,
        staged_k_relax=args.staged_k_relax,
        k_start=args.k_start,
        show_order=args.show_order,
        render_image=not args.no_render,
        out_path=args.out_path,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
