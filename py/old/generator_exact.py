from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations, product
from math import acos, atan2, pi, sqrt
from random import Random
import time
import os
from typing import Dict, List, Optional, Sequence, Set, Tuple


# =========================
# Exact numbers: Q(sqrt(2))
# =========================


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
        # (a + b r)(c + d r) = (ac + 2bd) + (ad + bc) r
        return Qsqrt2(self.a * o.a + 2 * self.b * o.b, self.a * o.b + self.b * o.a)

    def inv(self) -> "Qsqrt2":
        den = self.a * self.a - 2 * self.b * self.b
        if den == 0:
            raise ZeroDivisionError("singular Qsqrt2 inverse")
        return Qsqrt2(self.a / den, -self.b / den)

    def __truediv__(self, o: "Qsqrt2") -> "Qsqrt2":
        return self * o.inv()

    def __neg__(self) -> "Qsqrt2":
        return Qsqrt2(-self.a, -self.b)

    def approx(self) -> float:
        return float(self.a) + float(self.b) * (2.0**0.5)


ZERO = Qsqrt2.from_int(0)
ONE = Qsqrt2.from_int(1)
HALF = Qsqrt2.from_fraction(Fraction(1, 2))
SQRT2 = Qsqrt2(Fraction(0), Fraction(1))
INV_SQRT2 = Qsqrt2(Fraction(0), Fraction(1, 2))  # sqrt(2)/2
SQRT2_MINUS_ONE = Qsqrt2(Fraction(-1), Fraction(1))
SQRT2_PLUS_ONE = Qsqrt2(Fraction(1), Fraction(1))


@dataclass(frozen=True)
class PointE:
    x: Qsqrt2
    y: Qsqrt2

    def approx(self) -> Tuple[float, float]:
        return (self.x.approx(), self.y.approx())


EPS = 1e-9
ANGLE_COUNT = 16  # exact 22.5deg grid over Q(sqrt(2)) using non-unit direction vectors
_S = SQRT2_MINUS_ONE  # tan(22.5deg)
DIRS: List[Tuple[Qsqrt2, Qsqrt2]] = [
    (ONE, ZERO),  # 0
    (ONE, _S),  # 22.5
    (ONE, ONE),  # 45
    (_S, ONE),  # 67.5
    (ZERO, ONE),  # 90
    (-_S, ONE),  # 112.5
    (-ONE, ONE),  # 135
    (-ONE, _S),  # 157.5
    (-ONE, ZERO),  # 180
    (-ONE, -_S),  # 202.5
    (-ONE, -ONE),  # 225
    (-_S, -ONE),  # 247.5
    (ZERO, -ONE),  # 270
    (_S, -ONE),  # 292.5
    (ONE, -ONE),  # 315
    (ONE, -_S),  # 337.5
]


def _q2_sign(z: Qsqrt2) -> int:
    """
    Exact sign of z = a + b*sqrt(2).
    Returns -1, 0, +1.
    """
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
    # sa < 0 and sb > 0
    return 1 if bb2 > aa else -1


def _q2_cmp(x: Qsqrt2, y: Qsqrt2) -> int:
    return _q2_sign(x - y)


def cross(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2) -> Qsqrt2:
    return ax * by - ay * bx


def in_square(p: PointE, eps: float = EPS) -> bool:
    # Exact inclusion in [0,1]^2.
    return _q2_cmp(p.x, ZERO) >= 0 and _q2_cmp(p.x, ONE) <= 0 and _q2_cmp(p.y, ZERO) >= 0 and _q2_cmp(p.y, ONE) <= 0


def pt_key(p: PointE, tol: float = 1e-8) -> Tuple[Fraction, Fraction, Fraction, Fraction]:
    # Exact key in Q(sqrt(2)) coordinates.
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


def _q2_k_level(z: Qsqrt2) -> Optional[int]:
    ka = _v2_of_denominator(z.a)
    kb = _v2_of_denominator(z.b)
    if ka is None or kb is None:
        return None
    return max(ka, kb)


def _point_k_level(p: PointE) -> Optional[int]:
    kx = _q2_k_level(p.x)
    ky = _q2_k_level(p.y)
    if kx is None or ky is None:
        return None
    return max(kx, ky)


def _graph_within_k(g: "CreaseGraphExact", k_max: Optional[int]) -> bool:
    if k_max is None:
        return True
    for p in g.vertices:
        k = _point_k_level(p)
        if k is None or k > k_max:
            return False
    return True


@dataclass
class LineE:
    nx: Qsqrt2
    ny: Qsqrt2
    c: Qsqrt2


def make_line_through_point_dir(p: PointE, dir_idx: int) -> LineE:
    dx, dy = DIRS[dir_idx]
    nx, ny = -dy, dx
    c = nx * p.x + ny * p.y
    return LineE(nx, ny, c)


def line_intersection(l1: LineE, l2: LineE) -> Optional[PointE]:
    det = l1.nx * l2.ny - l1.ny * l2.nx
    if abs(det.approx()) < EPS:
        return None
    x = (l1.c * l2.ny - l2.c * l1.ny) / det
    y = (l1.nx * l2.c - l2.nx * l1.c) / det
    return PointE(x, y)


class CreaseGraphExact:
    def __init__(self, eps: float = EPS):
        self.eps = eps
        self.vertices: List[PointE] = []
        self.edges: Set[Tuple[int, int]] = set()
        self.edge_birth: Dict[Tuple[int, int], int] = {}
        self.edge_birth_counter = 0

    def add_vertex(self, p: PointE) -> int:
        k = pt_key(p)
        for i, q in enumerate(self.vertices):
            if pt_key(q) == k:
                return i
        self.vertices.append(p)
        return len(self.vertices) - 1

    def add_edge(self, i: int, j: int) -> None:
        if i == j:
            return
        e = (i, j) if i < j else (j, i)
        if e in self.edges:
            return
        self.edges.add(e)
        self.edge_birth[e] = self.edge_birth_counter
        self.edge_birth_counter += 1

    def remove_edge(self, i: int, j: int) -> None:
        e = (i, j) if i < j else (j, i)
        self.edges.discard(e)
        self.edge_birth.pop(e, None)

    def has_edge(self, i: int, j: int) -> bool:
        e = (i, j) if i < j else (j, i)
        return e in self.edges

    def init_square_boundary(self) -> None:
        v0 = self.add_vertex(PointE(ZERO, ZERO))
        v1 = self.add_vertex(PointE(ONE, ZERO))
        v2 = self.add_vertex(PointE(ONE, ONE))
        v3 = self.add_vertex(PointE(ZERO, ONE))
        self.add_edge(v0, v1)
        self.add_edge(v1, v2)
        self.add_edge(v2, v3)
        self.add_edge(v3, v0)

    def _ray_segment_hit(
        self,
        origin: PointE,
        d: Tuple[Qsqrt2, Qsqrt2],
        a: PointE,
        b: PointE,
    ) -> Optional[Tuple[Qsqrt2, Qsqrt2, PointE]]:
        vx, vy = b.x - a.x, b.y - a.y
        dx, dy = d
        denom = cross(dx, dy, vx, vy)
        if denom == ZERO:
            return None
        wx, wy = a.x - origin.x, a.y - origin.y
        t = cross(wx, wy, vx, vy) / denom
        u = cross(wx, wy, dx, dy) / denom
        if _q2_cmp(t, ZERO) <= 0:
            return None
        if _q2_cmp(u, ZERO) < 0 or _q2_cmp(u, ONE) > 0:
            return None
        p = PointE(origin.x + t * dx, origin.y + t * dy)
        return (t, u, p)

    def first_hit(self, origin_idx: int, dir_idx: int) -> Optional[Tuple[int, int, Qsqrt2, PointE]]:
        origin = self.vertices[origin_idx]
        d = DIRS[dir_idx]
        best_t: Optional[Qsqrt2] = None
        best: Optional[Tuple[int, int, Qsqrt2, PointE]] = None
        for i, j in self.edges:
            hit = self._ray_segment_hit(origin, d, self.vertices[i], self.vertices[j])
            if hit is None:
                continue
            t, u, p = hit
            if best_t is None or _q2_cmp(t, best_t) < 0:
                best_t = t
                best = (i, j, u, p)
        return best

    def shoot_ray_and_split(self, origin_idx: int, dir_idx: int) -> Optional[Tuple[int, int]]:
        hit = self.first_hit(origin_idx, dir_idx)
        if hit is None:
            return None
        i, j, u, p = hit
        if _q2_cmp(u, ZERO) <= 0:
            hit_idx = i
        elif _q2_cmp(u, ONE) >= 0:
            hit_idx = j
        else:
            hit_idx = self.add_vertex(p)
            self.remove_edge(i, j)
            self.add_edge(i, hit_idx)
            self.add_edge(hit_idx, j)
        if not self.has_edge(origin_idx, hit_idx):
            self.add_edge(origin_idx, hit_idx)
        return (origin_idx, hit_idx)


def clone_graph(g: CreaseGraphExact) -> CreaseGraphExact:
    h = CreaseGraphExact(eps=g.eps)
    h.vertices = list(g.vertices)
    h.edges = set(g.edges)
    h.edge_birth = dict(g.edge_birth)
    h.edge_birth_counter = g.edge_birth_counter
    return h


def mirror_point_y_eq_x(p: PointE) -> PointE:
    return PointE(p.y, p.x)


def mirrored_dir_idx(dir_idx: int) -> int:
    # Reflection across y=x: theta -> pi/2 - theta.
    return (4 - dir_idx) % ANGLE_COUNT


def find_vertex_idx(g: CreaseGraphExact, p: PointE, tol: float = 1e-8) -> Optional[int]:
    px, py = p.approx()
    for i, q in enumerate(g.vertices):
        qx, qy = q.approx()
        if abs(px - qx) <= tol and abs(py - qy) <= tol:
            return i
    return None


def diagonal_symmetry_ok(g: CreaseGraphExact, tol: float = 1e-8) -> bool:
    for i, j in g.edges:
        mi = find_vertex_idx(g, mirror_point_y_eq_x(g.vertices[i]), tol=tol)
        mj = find_vertex_idx(g, mirror_point_y_eq_x(g.vertices[j]), tol=tol)
        if mi is None or mj is None:
            return False
        e = (mi, mj) if mi < mj else (mj, mi)
        if e not in g.edges:
            return False
    return True


def apply_ray_action(
    g: CreaseGraphExact,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool = True,
) -> Optional[CreaseGraphExact]:
    h = clone_graph(g)
    if h.shoot_ray_and_split(v_idx, dir_idx) is None:
        return None
    if enforce_symmetry:
        mv = find_vertex_idx(h, mirror_point_y_eq_x(g.vertices[v_idx]), tol=1e-8)
        if mv is None:
            return None
        md = mirrored_dir_idx(dir_idx)
        if not (mv == v_idx and md == dir_idx):
            if h.shoot_ray_and_split(mv, md) is None:
                return None
        if not diagonal_symmetry_ok(h, tol=1e-8):
            return None
    return h


def _nearest_dir_idx(dx: float, dy: float) -> int:
    vn = (dx * dx + dy * dy) ** 0.5
    if vn <= 1e-15:
        return 0
    ux = dx / vn
    uy = dy / vn
    best_k = 0
    best = -1e100
    for k, (rx, ry) in enumerate(DIRS):
        rxf = rx.approx()
        ryf = ry.approx()
        rn = (rxf * rxf + ryf * ryf) ** 0.5
        if rn <= 1e-15:
            continue
        dot = ux * (rxf / rn) + uy * (ryf / rn)
        if dot > best:
            best = dot
            best_k = k
    return best_k


def _exact_dir_idx_from_delta(dx: Qsqrt2, dy: Qsqrt2) -> Optional[int]:
    """
    Return exact 16-direction index if (dx,dy) is collinear with one DIRS[k]
    over Q(sqrt(2)); otherwise None.
    """
    if dx == ZERO and dy == ZERO:
        return None
    for k, (rx, ry) in enumerate(DIRS):
        # collinear?
        if cross(dx, dy, rx, ry) != ZERO:
            continue
        dot = dx * rx + dy * ry
        s = _q2_sign(dot)
        if s > 0:
            return k
        if s < 0:
            return (k + ANGLE_COUNT // 2) % ANGLE_COUNT
    return None


def _reflected_dir_idx(dir_idx: int, a: PointE, b: PointE) -> int:
    dx, dy = DIRS[dir_idx]
    tx = (b.x - a.x).approx()
    ty = (b.y - a.y).approx()
    n = (tx * tx + ty * ty) ** 0.5
    if n <= 1e-15:
        return dir_idx
    tx /= n
    ty /= n
    vx = dx.approx()
    vy = dy.approx()
    dot = vx * tx + vy * ty
    # Open-sink propagation rule:
    # keep normal component, flip tangent component.
    # v' = v - 2 (v·t) t
    rx = vx - 2 * dot * tx
    ry = vy - 2 * dot * ty
    return _nearest_dir_idx(rx, ry)


def _is_boundary_point(p: PointE, tol: float = 1e-8) -> bool:
    x, y = p.approx()
    return abs(x) <= tol or abs(x - 1.0) <= tol or abs(y) <= tol or abs(y - 1.0) <= tol


def _is_square_corner(p: PointE, tol: float = 1e-8) -> bool:
    x, y = p.approx()
    return (
        (abs(x - 0.0) <= tol and abs(y - 0.0) <= tol)
        or (abs(x - 0.0) <= tol and abs(y - 1.0) <= tol)
        or (abs(x - 1.0) <= tol and abs(y - 0.0) <= tol)
        or (abs(x - 1.0) <= tol and abs(y - 1.0) <= tol)
    )


def _on_diag_y_eq_x(p: PointE, tol: float = 1e-8) -> bool:
    x, y = p.approx()
    return abs(x - y) <= tol


def _boundary_interval(p: PointE, eps: float = 1e-9) -> Optional[Tuple[float, float]]:
    x, y = p.approx()
    on_l = abs(x - 0.0) <= eps
    on_r = abs(x - 1.0) <= eps
    on_b = abs(y - 0.0) <= eps
    on_t = abs(y - 1.0) <= eps
    if on_l and on_b:
        return (0.0, pi / 2.0)
    if on_l and on_t:
        return (3.0 * pi / 2.0, 2.0 * pi)
    if on_r and on_t:
        return (pi, 3.0 * pi / 2.0)
    if on_r and on_b:
        return (pi / 2.0, pi)
    if on_b:
        return (0.0, pi)
    if on_t:
        return (pi, 2.0 * pi)
    if on_l:
        return (3.0 * pi / 2.0, pi / 2.0)
    if on_r:
        return (pi / 2.0, 3.0 * pi / 2.0)
    return None


def _normalize_angle(a: float) -> float:
    while a < 0:
        a += 2 * pi
    while a >= 2 * pi:
        a -= 2 * pi
    return a


def _in_ccw_interval(a: float, start: float, end: float, tol: float = 1e-10) -> bool:
    a = _normalize_angle(a)
    start = _normalize_angle(start)
    end = _normalize_angle(end)
    if start <= end:
        return start - tol <= a <= end + tol
    return a >= start - tol or a <= end + tol


def _interval_bisector(start: float, end: float) -> float:
    start = _normalize_angle(start)
    end = _normalize_angle(end)
    d = end - start
    if d < 0:
        d += 2 * pi
    return _normalize_angle(start + 0.5 * d)


def _angle_of_dir_idx(d: int) -> float:
    dx, dy = DIRS[d]
    a = atan2(dy.approx(), dx.approx())
    if a < 0:
        a += 2 * pi
    return a


def admissible_dirs_for_vertex(
    g: CreaseGraphExact,
    v_idx: int,
    enforce_symmetry: bool,
    tol: float = 1e-8,
) -> List[int]:
    p = g.vertices[v_idx]
    interval = _boundary_interval(p, eps=tol)
    dirs = list(range(ANGLE_COUNT))

    # Remove outward directions on boundary vertices.
    if interval is not None:
        s, e = interval
        dirs = [d for d in dirs if _in_ccw_interval(_angle_of_dir_idx(d), s, e, tol=tol)]

    if not enforce_symmetry:
        return dirs

    # On y=x axis, remove mirror-duplicate directions by canonicalization.
    if _on_diag_y_eq_x(p, tol=tol):
        canon: List[int] = []
        seen: Set[Tuple[int, int]] = set()
        for d in dirs:
            md = mirrored_dir_idx(d)
            pair = (d, md) if d <= md else (md, d)
            if pair in seen:
                continue
            seen.add(pair)
            # Avoid self-mirrored direction for open-sink seeds.
            if d == md:
                continue
            canon.append(min(d, md))
        dirs = canon

        # At square corners on y=x, bias to one representative near boundary wedge side
        # (e.g. (0,0): prefer 22.5deg representative).
        x, y = p.approx()
        if (abs(x) <= tol and abs(y) <= tol) or (abs(x - 1.0) <= tol and abs(y - 1.0) <= tol):
            if interval is not None and dirs:
                s, e = interval
                # Exclude rays exactly along boundary edges.
                dirs2 = []
                for d in dirs:
                    a = _angle_of_dir_idx(d)
                    if abs(a - _normalize_angle(s)) <= 1e-12 or abs(a - _normalize_angle(e)) <= 1e-12:
                        continue
                    dirs2.append(d)
                if dirs2:
                    dirs = dirs2
                b = _interval_bisector(s, e)
                dirs.sort(key=lambda d: abs(_angle_of_dir_idx(d) - b))
                dirs = dirs[:1]
    return dirs


def _expand_symmetric_fronts(
    g: CreaseGraphExact,
    fronts: Sequence[Tuple[int, int]],
    enforce_symmetry: bool,
) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    seen: Set[Tuple[int, int]] = set()
    for v, d in fronts:
        if (v, d) not in seen:
            seen.add((v, d))
            out.append((v, d))
        if not enforce_symmetry:
            continue
        mv = find_vertex_idx(g, mirror_point_y_eq_x(g.vertices[v]), tol=1e-8)
        if mv is None:
            continue
        md = mirrored_dir_idx(d)
        if (mv, md) not in seen:
            seen.add((mv, md))
            out.append((mv, md))
    return out


def _diag_kawasaki_repair(g: CreaseGraphExact, v_idx: int, tol: float = 1e-8) -> bool:
    """
    Try to satisfy Kawasaki at a y=x collision vertex by shooting a diagonal pair
    (45deg and 225deg). Returns True if the vertex becomes acceptable.
    """
    if corner_kawasaki_error(g, v_idx) <= tol:
        return True
    changed = False
    for d in (2, 10):  # y=x axis directions
        if g.shoot_ray_and_split(v_idx, d) is not None:
            changed = True
    if not changed:
        return False
    return corner_kawasaki_error(g, v_idx) <= tol


def _run_multi_ray_transaction(
    g: CreaseGraphExact,
    fronts_init: Sequence[Tuple[int, int]],
    enforce_symmetry: bool = True,
    max_bounces: int = 16,
) -> Optional[CreaseGraphExact]:
    if not fronts_init:
        return None
    h = clone_graph(g)
    ray_vs = [v for v, _ in fronts_init]
    ray_ds = [d for _, d in fronts_init]
    n = len(ray_vs)
    ray_done = [False] * n
    config_seen: Set[Tuple[Tuple[int, int], ...]] = set()

    def config() -> Tuple[Tuple[int, int], ...]:
        cur = []
        for i in range(n):
            cur.append((ray_vs[i], -1 if ray_done[i] else ray_ds[i]))
        cur.sort()
        return tuple(cur)

    def has_collision() -> bool:
        active = [ray_vs[i] for i in range(n) if not ray_done[i]]
        return len(active) != len(set(active))

    def collision_vertices() -> List[int]:
        active = [ray_vs[i] for i in range(n) if not ray_done[i]]
        cnt: Dict[int, int] = {}
        for v in active:
            cnt[v] = cnt.get(v, 0) + 1
        return [v for v, c in cnt.items() if c >= 2]

    config_seen.add(config())
    for _ in range(max_bounces):
        for rid in range(n):
            if ray_done[rid]:
                continue
            cur_v, cur_d = ray_vs[rid], ray_ds[rid]
            hit = h.first_hit(cur_v, cur_d)
            if hit is None:
                return None
            i, j, u, p_hit = hit
            a = h.vertices[i]
            b = h.vertices[j]
            if h.shoot_ray_and_split(cur_v, cur_d) is None:
                return None
            uf = u.approx()
            hit_interior = (uf > h.eps) and (uf < 1.0 - h.eps)
            if uf <= h.eps:
                next_v = find_vertex_idx(h, a, tol=1e-7)
            elif uf >= 1.0 - h.eps:
                next_v = find_vertex_idx(h, b, tol=1e-7)
            else:
                next_v = find_vertex_idx(h, p_hit, tol=1e-7)
            if next_v is None:
                return None
            ray_vs[rid] = next_v
            if _is_boundary_point(h.vertices[next_v], tol=1e-8):
                ray_done[rid] = True
            else:
                ray_ds[rid] = _reflected_dir_idx(cur_d, a, b)

        if has_collision():
            if enforce_symmetry:
                for cv in collision_vertices():
                    if _on_diag_y_eq_x(h.vertices[cv], tol=1e-8):
                        if corner_kawasaki_error(h, cv) > 1e-8:
                            if not _diag_kawasaki_repair(h, cv, tol=1e-8):
                                return None
            return h if (not enforce_symmetry or diagonal_symmetry_ok(h, tol=1e-8)) else None
        if all(ray_done):
            return h if (not enforce_symmetry or diagonal_symmetry_ok(h, tol=1e-8)) else None
        c = config()
        if c in config_seen:
            return h if (not enforce_symmetry or diagonal_symmetry_ok(h, tol=1e-8)) else None
        config_seen.add(c)
    return None


def _run_open_sink_transaction(
    g: CreaseGraphExact,
    fronts_init: Sequence[Tuple[int, int]],
    enforce_symmetry: bool = True,
    max_bounces: int = 16,
) -> Optional[CreaseGraphExact]:
    """
    Open-sink specific transaction:
    - one-ray track per front (no branching),
    - if a ray reaches y=x, stop that ray immediately,
    - if a ray hits an existing non-diagonal vertex, pick the next direction
      that prioritizes Kawasaki satisfaction and then smallest turn from the
      current direction.
    """
    if not fronts_init:
        return None
    h = clone_graph(g)
    ray_vs = [v for v, _ in fronts_init]
    ray_ds = [d for _, d in fronts_init]
    n = len(ray_vs)
    ray_done = [False] * n
    config_seen: Set[Tuple[Tuple[int, int], ...]] = set()
    diag_touched: Set[int] = set()

    def _dir_gap(a: int, b: int) -> int:
        d = abs(a - b) % ANGLE_COUNT
        return min(d, ANGLE_COUNT - d)

    def _next_dir_at_existing_vertex(v_idx: int, incoming_d: int) -> Optional[int]:
        used = set(_incident_dir_indices(h, v_idx))
        cand = [d for d in admissible_dirs_for_vertex(h, v_idx, enforce_symmetry=False) if d not in used]
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

    def config() -> Tuple[Tuple[int, int], ...]:
        cur = []
        for i in range(n):
            cur.append((ray_vs[i], -1 if ray_done[i] else ray_ds[i]))
        cur.sort()
        return tuple(cur)

    def has_collision() -> bool:
        active = [ray_vs[i] for i in range(n) if not ray_done[i]]
        return len(active) != len(set(active))

    config_seen.add(config())
    for _ in range(max_bounces):
        for rid in range(n):
            if ray_done[rid]:
                continue
            cur_v, cur_d = ray_vs[rid], ray_ds[rid]
            hit = h.first_hit(cur_v, cur_d)
            if hit is None:
                return None
            i, j, u, p_hit = hit
            a = h.vertices[i]
            b = h.vertices[j]
            if h.shoot_ray_and_split(cur_v, cur_d) is None:
                return None
            uf = u.approx()
            hit_interior = (uf > h.eps) and (uf < 1.0 - h.eps)
            if uf <= h.eps:
                next_v = find_vertex_idx(h, a, tol=1e-7)
            elif uf >= 1.0 - h.eps:
                next_v = find_vertex_idx(h, b, tol=1e-7)
            else:
                next_v = find_vertex_idx(h, p_hit, tol=1e-7)
            if next_v is None:
                return None
            ray_vs[rid] = next_v

            # User rule: stop immediately when reaching y=x (even on existing vertex).
            if _on_diag_y_eq_x(h.vertices[next_v], tol=1e-8):
                diag_touched.add(next_v)
                ray_done[rid] = True
                continue
            if _is_boundary_point(h.vertices[next_v], tol=1e-8):
                ray_done[rid] = True
                continue

            if hit_interior:
                # Interior hit on an existing edge: continuation is uniquely the
                # reflected direction with respect to the hit edge.
                ray_ds[rid] = _reflected_dir_idx(cur_d, a, b)
            else:
                # Endpoint / existing-vertex hit: choose next direction by local
                # Kawasaki priority and smallest turn.
                nd = _next_dir_at_existing_vertex(next_v, cur_d)
                if nd is None:
                    return None
                ray_ds[rid] = nd

        if has_collision() or all(ray_done):
            break
        c = config()
        if c in config_seen:
            break
        config_seen.add(c)

    # Optional post-repair at diagonal touch points.
    for v in sorted(diag_touched):
        if corner_kawasaki_error(h, v) > 1e-8:
            _diag_kawasaki_repair(h, v, tol=1e-8)

    if enforce_symmetry and not diagonal_symmetry_ok(h, tol=1e-8):
        return None
    return h


def _repair_open_sink_vertices(
    base: CreaseGraphExact,
    g: CreaseGraphExact,
    enforce_symmetry: bool,
    max_bounces: int,
    tol: float = 1e-8,
    max_rounds: int = 2,
) -> CreaseGraphExact:
    """
    Open-sink post repair:
    try one additional open-sink shot from violating interior vertices and keep
    only strictly improving repairs.
    """
    h = clone_graph(g)
    for _ in range(max_rounds):
        targets = [
            v
            for v in range(len(h.vertices))
            if (not _is_boundary_point(h.vertices[v], tol=1e-8)) and corner_kawasaki_error(h, v) > tol
        ]
        if not targets:
            return h
        progressed = False
        for v in targets:
            before_ke = corner_kawasaki_error(h, v)
            before_total = sum(
                corner_kawasaki_error(h, u)
                for u in range(len(h.vertices))
                if not _is_boundary_point(h.vertices[u], tol=1e-8)
            )
            used = set(_incident_dir_indices(h, v))
            cand = [d for d in admissible_dirs_for_vertex(h, v, enforce_symmetry=enforce_symmetry) if d not in used]
            if not cand:
                continue
            best_h: Optional[CreaseGraphExact] = None
            best_key: Optional[Tuple[float, float]] = None
            for d in cand:
                fronts = _expand_symmetric_fronts(h, [(v, d)], enforce_symmetry=enforce_symmetry)
                hh = _run_open_sink_transaction(
                    h,
                    fronts,
                    enforce_symmetry=enforce_symmetry,
                    max_bounces=max_bounces,
                )
                if hh is None:
                    continue
                after_ke = corner_kawasaki_error(hh, v)
                after_total = sum(
                    corner_kawasaki_error(hh, u)
                    for u in range(len(hh.vertices))
                    if not _is_boundary_point(hh.vertices[u], tol=1e-8)
                )
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


def apply_open_sink_action(
    g: CreaseGraphExact,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool = True,
    max_bounces: int = 16,
) -> Optional[CreaseGraphExact]:
    # Open sink (single-ray track per side):
    # - always launch one seed ray from (v_idx, dir_idx),
    # - when symmetry is enabled, launch the mirrored counterpart as well.
    # Each track then propagates as a single reflected ray.
    # After transactional success, run a lightweight Kawasaki repair on newly
    # created interior vertices before returning.
    h0 = clone_graph(g)
    fronts: List[Tuple[int, int]] = [(v_idx, dir_idx)]
    if enforce_symmetry:
        mp = mirror_point_y_eq_x(h0.vertices[v_idx])
        mv = find_vertex_idx(h0, mp, tol=1e-8)
        if mv is None:
            mv = h0.add_vertex(mp)
        fronts.append((mv, mirrored_dir_idx(dir_idx)))
    # Deduplicate starts.
    uniq: List[Tuple[int, int]] = []
    seen: Set[Tuple[int, int]] = set()
    for f in fronts:
        if f in seen:
            continue
        seen.add(f)
        uniq.append(f)
    out = _run_open_sink_transaction(
        h0,
        uniq,
        enforce_symmetry=enforce_symmetry,
        max_bounces=max_bounces,
    )
    if out is None:
        return None
    # Open-sink specific repair.
    out = _repair_open_sink_vertices(
        g,
        out,
        enforce_symmetry=enforce_symmetry,
        max_bounces=max_bounces,
    )
    if enforce_symmetry and not diagonal_symmetry_ok(out, tol=1e-8):
        return None
    return out


def _tsumami_repair_pair_candidates(
    g: CreaseGraphExact,
    hit_v: int,
    legacy_pair: Tuple[int, int],
    kawasaki_tol: float = 1e-8,
    max_bounces: int = 8,
) -> List[Tuple[int, int]]:
    """
    Enumerate all direction pairs (d1,d2) that can be shot from hit_v and
    make hit_v satisfy Kawasaki after the two shots.
    """
    dirs = admissible_dirs_for_vertex(g, hit_v, enforce_symmetry=False)
    if len(dirs) < 2:
        return [legacy_pair]

    def _ray_hits_existing_vertex(v_idx: int, d: int) -> bool:
        hit = g.first_hit(v_idx, d)
        if hit is None:
            return False
        _, _, u, p_hit = hit
        uf = u.approx()
        if uf <= g.eps or uf >= 1.0 - g.eps:
            return True
        return find_vertex_idx(g, p_hit, tol=1e-7) is not None

    out: List[Tuple[int, int]] = []
    seen: Set[Tuple[int, int]] = set()
    base_dirs = set(_incident_dir_indices(g, hit_v))
    for d1, d2 in combinations(sorted(set(dirs)), 2):
        # Constraint: at least one of the two repair rays must pass through
        # an existing vertex.
        if not (_ray_hits_existing_vertex(hit_v, d1) or _ray_hits_existing_vertex(hit_v, d2)):
            continue
        # Pre-check local 4-ray consistency before propagation:
        # incoming + remaining edge(s) + two repair rays should already satisfy
        # Kawasaki at hit_v.
        local_dirs = sorted(base_dirs | {d1, d2})
        if _kawasaki_residual_from_dirs(local_dirs) > kawasaki_tol:
            continue
        # Simulate repair propagation with the same reflection rule as open sink.
        t = _run_multi_ray_transaction(
            g,
            [(hit_v, d1), (hit_v, d2)],
            enforce_symmetry=False,
            max_bounces=max_bounces,
        )
        if t is None:
            continue
        ke = corner_kawasaki_error(t, hit_v)
        if ke <= kawasaki_tol:
            pair = (d1, d2) if d1 <= d2 else (d2, d1)
            if pair not in seen:
                seen.add(pair)
                out.append(pair)
    if not out:
        return [legacy_pair]
    return out


def apply_tsumami_action_variants(
    g: CreaseGraphExact,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool = True,
    max_bounces: int = 16,
    delete_shorter_side: bool = True,
) -> List[CreaseGraphExact]:
    seed_fronts = _expand_symmetric_fronts(g, [(v_idx, dir_idx)], enforce_symmetry=enforce_symmetry)
    if not seed_fronts:
        return []
    h = clone_graph(g)
    # For each local tsumami hit vertex, collect all repair-pair candidates.
    per_vertex_pairs: List[Tuple[int, List[Tuple[int, int]]]] = []

    for sv, sd in seed_fronts:
        hit = h.first_hit(sv, sd)
        if hit is None:
            return []
        i, j, u, p_hit = hit
        a, b = h.vertices[i], h.vertices[j]
        if h.shoot_ray_and_split(sv, sd) is None:
            return []
        uf = u.approx()
        if uf <= h.eps:
            hit_v = find_vertex_idx(h, a, tol=1e-7)
        elif uf >= 1.0 - h.eps:
            hit_v = find_vertex_idx(h, b, tol=1e-7)
        else:
            hit_v = find_vertex_idx(h, p_hit, tol=1e-7)
        if hit_v is None:
            return []
        if _is_boundary_point(h.vertices[hit_v], tol=1e-8):
            continue
        # complete tsumami: delete one side segment.
        # Choose shorter or longer side by option.
        ai = find_vertex_idx(h, a, tol=1e-7)
        bj = find_vertex_idx(h, b, tol=1e-7)
        if ai is None or bj is None:
            return []
        hx, hy = h.vertices[hit_v].approx()
        ax, ay = h.vertices[ai].approx()
        bx, by = h.vertices[bj].approx()
        la2 = (ax - hx) * (ax - hx) + (ay - hy) * (ay - hy)
        lb2 = (bx - hx) * (bx - hx) + (by - hy) * (by - hy)
        del_to = ai if (la2 <= lb2) == delete_shorter_side else bj
        h.remove_edge(hit_v, del_to)
        legacy_pair = (
            _reflected_dir_idx(sd, a, b),
            _reflected_dir_idx((sd + ANGLE_COUNT // 2) % ANGLE_COUNT, a, b),
        )
        pair_cands = _tsumami_repair_pair_candidates(
            h,
            hit_v,
            legacy_pair,
            kawasaki_tol=1e-8,
            max_bounces=max_bounces,
        )
        per_vertex_pairs.append((hit_v, pair_cands))

    if not per_vertex_pairs:
        if enforce_symmetry and not diagonal_symmetry_ok(h, tol=1e-8):
            return []
        return [h]

    all_out: List[CreaseGraphExact] = []
    pair_lists = [pairs for _, pairs in per_vertex_pairs]
    for choice in product(*pair_lists):
        repair_fronts: List[Tuple[int, int]] = []
        for (hit_v, _), (d1, d2) in zip(per_vertex_pairs, choice):
            repair_fronts.append((hit_v, d1))
            repair_fronts.append((hit_v, d2))
        repair_fronts = _expand_symmetric_fronts(h, repair_fronts, enforce_symmetry=enforce_symmetry)
        out = _run_multi_ray_transaction(
            h,
            repair_fronts,
            enforce_symmetry=enforce_symmetry,
            max_bounces=max_bounces,
        )
        if out is not None:
            all_out.append(out)
    return all_out


def apply_tsumami_action(
    g: CreaseGraphExact,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool = True,
    max_bounces: int = 16,
    delete_shorter_side: bool = True,
) -> Optional[CreaseGraphExact]:
    outs = apply_tsumami_action_variants(
        g,
        v_idx,
        dir_idx,
        enforce_symmetry=enforce_symmetry,
        max_bounces=max_bounces,
        delete_shorter_side=delete_shorter_side,
    )
    return outs[0] if outs else None


def _new_internal_vertex_ids(base: CreaseGraphExact, cur: CreaseGraphExact) -> List[int]:
    base_keys = {pt_key(p) for p in base.vertices}
    out: List[int] = []
    for i, p in enumerate(cur.vertices):
        if pt_key(p) in base_keys:
            continue
        if _is_boundary_point(p, tol=1e-8):
            continue
        out.append(i)
    return out


def _repair_triangle_macro_new_vertices(
    base: CreaseGraphExact,
    g: CreaseGraphExact,
    enforce_symmetry: bool,
    max_bounces: int,
    launch_vertices: Sequence[int] = (),
    corner_max_deg: Optional[float] = None,
    tol: float = 1e-8,
    max_rounds: int = 4,
    deadline_ts: Optional[float] = None,
) -> CreaseGraphExact:
    """
    Post-repair for triangle macro:
    for each newly created interior vertex I, shoot 1/2 rays from I such that
    local directions satisfy Kawasaki, then propagate with the same multi-ray
    reflection transaction as open-sink.
    """
    h = clone_graph(g)
    def _needs_repair(gg: CreaseGraphExact, v_idx: int) -> bool:
        if corner_kawasaki_error(gg, v_idx) > tol:
            return True
        if (
            corner_max_deg is not None
            and corner_condition_error(gg, v_idx, max_deg=corner_max_deg) > tol
        ):
            return True
        return False

    launch_set = set(launch_vertices)
    for _ in range(max_rounds):
        if deadline_ts is not None and time.time() >= deadline_ts:
            return h
        targets: Set[int] = set(_new_internal_vertex_ids(base, h))
        # Launch-vertex repair rule:
        # - interior only
        # - odd degree only
        # - skip y=x axis vertices under symmetric mode
        for v in launch_set:
            if not (0 <= v < len(h.vertices)):
                continue
            if _is_boundary_point(h.vertices[v], tol=1e-8):
                continue
            if enforce_symmetry and _on_diag_y_eq_x(h.vertices[v], tol=1e-8):
                continue
            if len(_incident_dir_indices(h, v)) % 2 == 1:
                targets.add(v)
        bad = [v for v in sorted(targets) if _needs_repair(h, v)]
        if not bad:
            return h

        progressed = False
        for v in bad:
            if deadline_ts is not None and time.time() >= deadline_ts:
                return h
            used = set(_incident_dir_indices(h, v))
            dirs = [d for d in admissible_dirs_for_vertex(h, v, enforce_symmetry=False) if d not in used]
            if not dirs:
                continue

            cands: List[List[Tuple[int, int]]] = []
            is_launch_target = v in launch_set
            for d in dirs:
                local = sorted(used | {d})
                if _kawasaki_residual_from_dirs(local) <= tol:
                    cands.append([(v, d)])
            # For launch-point repair, user requested one-ray repair only.
            if not is_launch_target:
                for d1, d2 in combinations(dirs, 2):
                    local = sorted(used | {d1, d2})
                    if _kawasaki_residual_from_dirs(local) <= tol:
                        cands.append([(v, d1), (v, d2)])
            if not cands:
                continue

            before_k = corner_kawasaki_error(h, v)
            before_c = (
                corner_condition_error(h, v, max_deg=corner_max_deg)
                if corner_max_deg is not None
                else 0.0
            )
            best_h: Optional[CreaseGraphExact] = None
            best_key: Optional[Tuple[int, int, float, float]] = None
            for fronts in cands:
                if deadline_ts is not None and time.time() >= deadline_ts:
                    return h
                use_fronts = _expand_symmetric_fronts(h, fronts, enforce_symmetry=enforce_symmetry)
                hh = _run_multi_ray_transaction(
                    h,
                    use_fronts,
                    enforce_symmetry=enforce_symmetry,
                    max_bounces=max_bounces,
                )
                if hh is None:
                    continue
                after_k = corner_kawasaki_error(hh, v)
                after_c = (
                    corner_condition_error(hh, v, max_deg=corner_max_deg)
                    if corner_max_deg is not None
                    else 0.0
                )
                bad_new = sum(
                    1 for u in _new_internal_vertex_ids(base, hh) if _needs_repair(hh, u)
                )
                key = (
                    0 if after_k <= tol else 1,
                    bad_new,
                    after_c,
                    after_k,
                )
                if best_key is None or key < best_key:
                    best_key = key
                    best_h = hh

            if best_h is None or best_key is None:
                continue
            if (
                best_key[2] < before_c - 1e-12
                or best_key[3] < before_k - 1e-12
                or best_key[0] == 0
            ):
                h = best_h
                progressed = True
                break
        if not progressed:
            break
    return h


def _angle_between(u: Tuple[float, float], v: Tuple[float, float]) -> float:
    ux, uy = u
    vx, vy = v
    nu = sqrt(ux * ux + uy * uy)
    nv = sqrt(vx * vx + vy * vy)
    if nu < 1e-12 or nv < 1e-12:
        return 0.0
    c = (ux * vx + uy * vy) / (nu * nv)
    c = max(-1.0, min(1.0, c))
    return acos(c) * 180.0 / pi


def _add_segment_with_splits(g: CreaseGraphExact, p: PointE, q: PointE, eps: float = 1e-9) -> bool:
    """
    Insert segment p-q into graph by splitting crossed edges and then connecting
    consecutive points on the segment.
    """
    if p == q:
        return False

    p_idx = g.add_vertex(p)
    q_idx = g.add_vertex(q)

    points_on_seg: List[Tuple[float, int]] = [(0.0, p_idx), (1.0, q_idx)]
    edges_snapshot = list(g.edges)
    for i, j in edges_snapshot:
        a = g.vertices[i]
        b = g.vertices[j]
        r = (q.x - p.x, q.y - p.y)
        s = (b.x - a.x, b.y - a.y)
        den = cross(r[0], r[1], s[0], s[1])
        if den == ZERO:
            continue
        qmp = (a.x - p.x, a.y - p.y)
        t = cross(qmp[0], qmp[1], s[0], s[1]) / den
        u = cross(qmp[0], qmp[1], r[0], r[1]) / den
        if _q2_cmp(t, ZERO) <= 0 or _q2_cmp(t, ONE) >= 0:
            continue
        tf = t.approx()
        if _q2_cmp(u, ZERO) <= 0:
            points_on_seg.append((tf, i))
            continue
        if _q2_cmp(u, ONE) >= 0:
            points_on_seg.append((tf, j))
            continue
        ip = PointE(p.x + t * r[0], p.y + t * r[1])
        mid_idx = g.add_vertex(ip)
        g.remove_edge(i, j)
        g.add_edge(i, mid_idx)
        g.add_edge(mid_idx, j)
        points_on_seg.append((tf, mid_idx))

    points_on_seg.sort(key=lambda x: x[0])
    dedup: List[int] = []
    for _, vid in points_on_seg:
        if not dedup or dedup[-1] != vid:
            dedup.append(vid)
    changed = False
    for u, v in zip(dedup, dedup[1:]):
        if not g.has_edge(u, v):
            g.add_edge(u, v)
            changed = True
    return changed


def _triangle_angles_deg(
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
) -> Tuple[float, float, float]:
    ax, ay = a
    bx, by = b
    cx, cy = c
    A = _angle_between((bx - ax, by - ay), (cx - ax, cy - ay))
    B = _angle_between((ax - bx, ay - by), (cx - bx, cy - by))
    C = _angle_between((ax - cx, ay - cy), (bx - cx, by - cy))
    return (A, B, C)


def _nearest_dir_idx_from_vec(dx: float, dy: float) -> int:
    return _nearest_dir_idx(dx, dy)


def _bisector_dir_idx(center: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float]) -> int:
    cx, cy = center
    x1, y1 = p1
    x2, y2 = p2
    v1 = (x1 - cx, y1 - cy)
    v2 = (x2 - cx, y2 - cy)
    n1 = sqrt(v1[0] * v1[0] + v1[1] * v1[1])
    n2 = sqrt(v2[0] * v2[0] + v2[1] * v2[1])
    if n1 < 1e-12 and n2 < 1e-12:
        return 0
    if n1 < 1e-12:
        return _nearest_dir_idx_from_vec(v2[0], v2[1])
    if n2 < 1e-12:
        return _nearest_dir_idx_from_vec(v1[0], v1[1])
    bx = v1[0] / n1 + v2[0] / n2
    by = v1[1] / n1 + v2[1] / n2
    if abs(bx) < 1e-12 and abs(by) < 1e-12:
        # opposite vectors: fallback to one direction
        return _nearest_dir_idx_from_vec(v1[0], v1[1])
    return _nearest_dir_idx_from_vec(bx, by)


def _minor_turn_step(d0: int, d1: int) -> int:
    cw = (d0 - d1) % ANGLE_COUNT
    ccw = (d1 - d0) % ANGLE_COUNT
    return 1 if ccw <= cw else -1


def _triangle_macro_centers_for_triplet(
    g: CreaseGraphExact,
    va: int,
    vb: int,
    vc: int,
    angle_tol_deg: float = 6.0,
) -> List[Tuple[PointE, Tuple[int, int, int]]]:
    """
    Explicit macro centers:
    - (45,67.5,67.5): P/Q from A-bisector and B-angle trisectors.
    - (45,45,90): incenter I from two bisectors.
    Returns list of (center_point, (A,B,C)).
    """
    pa = g.vertices[va].approx()
    pb = g.vertices[vb].approx()
    pc = g.vertices[vc].approx()
    # Macro is defined on 16-direction triangles only.
    if not _is_aligned_with_16_dirs(g.vertices[va], g.vertices[vb]):
        return []
    if not _is_aligned_with_16_dirs(g.vertices[vb], g.vertices[vc]):
        return []
    if not _is_aligned_with_16_dirs(g.vertices[vc], g.vertices[va]):
        return []
    vids = [va, vb, vc]
    pts = [pa, pb, pc]

    def _minor_gap_steps(d0: int, d1: int) -> int:
        a = (d0 - d1) % ANGLE_COUNT
        b = (d1 - d0) % ANGLE_COUNT
        return min(a, b)

    # Angle at each vertex in 22.5deg steps (strict 16-dir classification).
    # 45deg -> 2 steps, 67.5deg -> 3 steps, 90deg -> 4 steps.
    steps: List[int] = []
    for i in range(3):
        j, k = [t for t in range(3) if t != i]
        pi = pts[i]
        pj = pts[j]
        pk = pts[k]
        dij = _nearest_dir_idx(pj[0] - pi[0], pj[1] - pi[1])
        dik = _nearest_dir_idx(pk[0] - pi[0], pk[1] - pi[1])
        steps.append(_minor_gap_steps(dij, dik))

    out: List[Tuple[PointE, Tuple[int, int, int]]] = []
    srt = sorted(steps)

    # Case 1: (45, 67.5, 67.5) -> (2,3,3)
    if srt == [2, 3, 3]:
        iA = steps.index(2)
        rem = [i for i in range(3) if i != iA]
        iB, iC = rem[0], rem[1]
        vA, vB, vC = vids[iA], vids[iB], vids[iC]
        pA, pB, pC = pts[iA], pts[iB], pts[iC]

        dAB = _nearest_dir_idx(pB[0] - pA[0], pB[1] - pA[1])
        dAC = _nearest_dir_idx(pC[0] - pA[0], pC[1] - pA[1])
        sA = _minor_turn_step(dAB, dAC)
        dL = (dAB + sA) % ANGLE_COUNT  # bisector of 45deg corner

        dBA = _nearest_dir_idx(pA[0] - pB[0], pA[1] - pB[1])
        dBC = _nearest_dir_idx(pC[0] - pB[0], pC[1] - pB[1])
        sB = _minor_turn_step(dBA, dBC)
        dM = (dBA + sB) % ANGLE_COUNT
        dN = (dBA + 2 * sB) % ANGLE_COUNT

        lA = make_line_through_point_dir(g.vertices[vA], dL)
        mB = make_line_through_point_dir(g.vertices[vB], dM)
        nB = make_line_through_point_dir(g.vertices[vB], dN)
        pP = line_intersection(lA, mB)
        pQ = line_intersection(lA, nB)
        if pP is not None and in_square(pP):
            out.append((pP, (vA, vB, vC)))
        if pQ is not None and in_square(pQ):
            out.append((pQ, (vA, vB, vC)))

    # Case 2: (45, 45, 90) -> (2,2,4)
    if srt == [2, 2, 4]:
        iR = steps.index(4)
        rem = [i for i in range(3) if i != iR]
        iU, iV = rem[0], rem[1]
        vU, vV, vR = vids[iU], vids[iV], vids[iR]
        pU, pV, pR = pts[iU], pts[iV], pts[iR]
        dU = _bisector_dir_idx(pU, pR, pV)
        dV = _bisector_dir_idx(pV, pR, pU)
        lU = make_line_through_point_dir(g.vertices[vU], dU)
        lV = make_line_through_point_dir(g.vertices[vV], dV)
        pI = line_intersection(lU, lV)
        if pI is not None and in_square(pI):
            out.append((pI, (vids[0], vids[1], vids[2])))

    return out


def _point_in_triangle_strict(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
    eps: float = 1e-10,
) -> bool:
    def sgn(p1: Tuple[float, float], p2: Tuple[float, float], p3: Tuple[float, float]) -> float:
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1 = sgn(p, a, b)
    d2 = sgn(p, b, c)
    d3 = sgn(p, c, a)
    has_neg = (d1 < -eps) or (d2 < -eps) or (d3 < -eps)
    has_pos = (d1 > eps) or (d2 > eps) or (d3 > eps)
    if has_neg and has_pos:
        return False
    # strict interior only (exclude boundary-near)
    return abs(d1) > eps and abs(d2) > eps and abs(d3) > eps


def _interior_edge_count_in_triangle(g: CreaseGraphExact, va: int, vb: int, vc: int) -> int:
    a = g.vertices[va].approx()
    b = g.vertices[vb].approx()
    c = g.vertices[vc].approx()
    tri_side = {
        (min(va, vb), max(va, vb)),
        (min(vb, vc), max(vb, vc)),
        (min(vc, va), max(vc, va)),
    }
    cnt = 0
    for i, j in g.edges:
        e = (min(i, j), max(i, j))
        if e in tri_side:
            continue
        pi = g.vertices[i].approx()
        pj = g.vertices[j].approx()
        m = ((pi[0] + pj[0]) * 0.5, (pi[1] + pj[1]) * 0.5)
        if _point_in_triangle_strict(m, a, b, c):
            cnt += 1
    return cnt


def _triangle_macro_fronts_for_triplet(
    g: CreaseGraphExact,
    va: int,
    vb: int,
    vc: int,
    angle_tol_deg: float = 6.0,
) -> List[List[Tuple[int, int]]]:
    pa = g.vertices[va].approx()
    pb = g.vertices[vb].approx()
    pc = g.vertices[vc].approx()
    A, B, C = _triangle_angles_deg(pa, pb, pc)
    angs = [A, B, C]
    vids = [va, vb, vc]
    pts = [pa, pb, pc]

    def _is_close(x: float, t: float) -> bool:
        return abs(x - t) <= angle_tol_deg

    out: List[List[Tuple[int, int]]] = []

    # Case 1: (45, 67.5, 67.5)
    sorted_angs = sorted(angs)
    if _is_close(sorted_angs[0], 45.0) and _is_close(sorted_angs[1], 67.5) and _is_close(sorted_angs[2], 67.5):
        idx45 = min(range(3), key=lambda i: abs(angs[i] - 45.0))
        idxs67 = [i for i in range(3) if i != idx45]
        iA = idx45
        iB, iC = idxs67[0], idxs67[1]
        vA, vB, vC = vids[iA], vids[iB], vids[iC]
        pA, pB, pC = pts[iA], pts[iB], pts[iC]

        dA = _bisector_dir_idx(pA, pB, pC)
        dC = _bisector_dir_idx(pC, pA, pB)

        # dB: 45deg from BC (two choices), keep both as variants.
        bcx, bcy = (pC[0] - pB[0], pC[1] - pB[1])
        # rotate +/- 45deg
        r = 2.0 ** 0.5 / 2.0
        cand_vecs = [
            (bcx * r - bcy * r, bcx * r + bcy * r),
            (bcx * r + bcy * r, -bcx * r + bcy * r),
        ]
        for vx, vy in cand_vecs:
            dB = _nearest_dir_idx_from_vec(vx, vy)
            out.append([(vA, dA), (vB, dB), (vC, dC)])

    # Case 2: right isosceles (45, 45, 90)
    if _is_close(sorted_angs[0], 45.0) and _is_close(sorted_angs[1], 45.0) and _is_close(sorted_angs[2], 90.0):
        d0 = _bisector_dir_idx(pa, pb, pc)
        d1 = _bisector_dir_idx(pb, pa, pc)
        d2 = _bisector_dir_idx(pc, pa, pb)
        out.append([(va, d0), (vb, d1), (vc, d2)])

    return out


def apply_triangle_macro_variants(
    g: CreaseGraphExact,
    anchor_v: int,
    enforce_symmetry: bool = True,
    max_bounces: int = 8,
    max_other_vertices: int = 8,
    corner_max_deg: Optional[float] = None,
    deadline_ts: Optional[float] = None,
) -> List[CreaseGraphExact]:
    """
    Triangle macro candidates from existing vertices (no edge-adjacency requirement).
    """
    ax, ay = g.vertices[anchor_v].approx()
    # Symmetry-side pruning: in y=x symmetric search, only expand one side.
    if enforce_symmetry and ax > ay + 1e-10:
        return []
    others = [i for i in range(len(g.vertices)) if i != anchor_v]
    others.sort(
        key=lambda i: (
            (g.vertices[i].approx()[0] - ax) ** 2 + (g.vertices[i].approx()[1] - ay) ** 2
        )
    )
    others = others[:max_other_vertices]
    out: List[CreaseGraphExact] = []
    seen: Set[Tuple] = set()
    dbg_non16 = os.getenv("TRI_NON16_DEBUG", "").strip() == "1"
    for i, j in combinations(others, 2):
        if deadline_ts is not None and time.time() >= deadline_ts:
            return out
        # Prune complex interiors: if triangle interior already has many edges,
        # triangle macro tends to explode in repair branches.
        if _interior_edge_count_in_triangle(g, anchor_v, i, j) > 1:
            continue
        centers = _triangle_macro_centers_for_triplet(g, anchor_v, i, j)
        for center, (vA, vB, vC) in centers:
            if deadline_ts is not None and time.time() >= deadline_ts:
                return out
            # Build no-delete + delete-one variants along launch directions.
            launch = [(vA, center), (vB, center), (vC, center)]
            base_states: List[CreaseGraphExact] = [g]
            base_keys: Set[Tuple] = {graph_state_key_exact(g)}
            removable: Set[Tuple[int, int]] = set()
            for sv, cp in launch:
                sx, sy = g.vertices[sv].approx()
                cx, cy = cp.approx()
                sd = _nearest_dir_idx(cx - sx, cy - sy)
                for a, b in g.edges:
                    if a != sv and b != sv:
                        continue
                    u = b if a == sv else a
                    ux, uy = g.vertices[u].approx()
                    ed = _nearest_dir_idx(ux - sx, uy - sy)
                    if ed == sd or ed == (sd + ANGLE_COUNT // 2) % ANGLE_COUNT:
                        e = (a, b) if a < b else (b, a)
                        removable.add(e)
            for u, v in removable:
                h0 = clone_graph(g)
                h0.remove_edge(u, v)
                if enforce_symmetry:
                    mu = find_vertex_idx(h0, mirror_point_y_eq_x(h0.vertices[u]), tol=1e-8)
                    mv = find_vertex_idx(h0, mirror_point_y_eq_x(h0.vertices[v]), tol=1e-8)
                    if mu is None or mv is None:
                        continue
                    if h0.has_edge(mu, mv):
                        h0.remove_edge(mu, mv)
                k0 = graph_state_key_exact(h0)
                if k0 in base_keys:
                    continue
                base_keys.add(k0)
                base_states.append(h0)

            for base in base_states:
                if deadline_ts is not None and time.time() >= deadline_ts:
                    return out
                h = clone_graph(base)
                edges_before = set(h.edges)
                cidx = h.add_vertex(center)
                changed = False
                for sv in (vA, vB, vC):
                    changed = _add_segment_with_splits(h, h.vertices[sv], h.vertices[cidx]) or changed
                if enforce_symmetry:
                    mc = mirror_point_y_eq_x(h.vertices[cidx])
                    mcidx = h.add_vertex(mc)
                    for sv in (vA, vB, vC):
                        mv = find_vertex_idx(h, mirror_point_y_eq_x(h.vertices[sv]), tol=1e-8)
                        if mv is None:
                            changed = False
                            break
                        changed = _add_segment_with_splits(h, h.vertices[mv], h.vertices[mcidx]) or changed
                    if not diagonal_symmetry_ok(h, tol=1e-8):
                        continue
                if not changed:
                    continue
                if dbg_non16:
                    bad_edges: List[Tuple[int, int]] = []
                    for e in h.edges:
                        if e in edges_before:
                            continue
                        i, j = e
                        if not _is_aligned_with_16_dirs(h.vertices[i], h.vertices[j]):
                            bad_edges.append(e)
                    if bad_edges:
                        tri_pts = [
                            h.vertices[vA].approx(),
                            h.vertices[vB].approx(),
                            h.vertices[vC].approx(),
                        ]
                        cen = h.vertices[cidx].approx()
                        bad_repr = [(h.vertices[i].approx(), h.vertices[j].approx()) for i, j in bad_edges]
                        print(
                            "[tri_non16]",
                            {
                                "triangle": tri_pts,
                                "center": cen,
                                "bad_edges": bad_repr,
                            },
                        )
                h = _repair_triangle_macro_new_vertices(
                    base,
                    h,
                    enforce_symmetry=enforce_symmetry,
                    max_bounces=max_bounces,
                    launch_vertices=[vA, vB, vC],
                    corner_max_deg=corner_max_deg,
                    deadline_ts=deadline_ts,
                )
                if enforce_symmetry and not diagonal_symmetry_ok(h, tol=1e-8):
                    continue
                k = graph_state_key_exact(h)
                if k in seen:
                    continue
                seen.add(k)
                out.append(h)
    return out


def _incident_dir_indices(g: CreaseGraphExact, v_idx: int) -> List[int]:
    vp = g.vertices[v_idx]
    dirs: Set[int] = set()
    for i, j in g.edges:
        if i != v_idx and j != v_idx:
            continue
        u = j if i == v_idx else i
        up = g.vertices[u]
        dx = up.x - vp.x
        dy = up.y - vp.y
        if dx == ZERO and dy == ZERO:
            continue
        k = _exact_dir_idx_from_delta(dx, dy)
        if k is None:
            # Fallback for legacy/non-16 edges.
            k = _nearest_dir_idx(dx.approx(), dy.approx())
        dirs.add(k)
    out = sorted(dirs)
    return out


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


def _boundary_interval_idx(p: PointE, eps: float = 1e-9) -> Optional[Tuple[int, int]]:
    x, y = p.approx()
    on_l = abs(x - 0.0) <= eps
    on_r = abs(x - 1.0) <= eps
    on_b = abs(y - 0.0) <= eps
    on_t = abs(y - 1.0) <= eps
    if on_l and on_b:
        return (0, 4)
    if on_l and on_t:
        return (12, 0)
    if on_r and on_t:
        return (8, 12)
    if on_r and on_b:
        return (4, 8)
    if on_b:
        return (0, 8)
    if on_t:
        return (8, 0)
    if on_l:
        return (12, 4)
    if on_r:
        return (4, 12)
    return None


def _in_ccw_interval_idx(d: int, start: int, end: int) -> bool:
    span = (end - start) % ANGLE_COUNT
    rel = (d - start) % ANGLE_COUNT
    return rel <= span


def _sector_steps_boundary(sorted_dirs: Sequence[int], start: int, end: int) -> List[int]:
    span = (end - start) % ANGLE_COUNT
    rels = sorted(set((d - start) % ANGLE_COUNT for d in sorted_dirs if _in_ccw_interval_idx(d, start, end)))
    rels = sorted(set([0, span, *rels]))
    if len(rels) < 2:
        return []
    return [rels[i + 1] - rels[i] for i in range(len(rels) - 1)]


def corner_condition_error(
    g: CreaseGraphExact,
    v_idx: int,
    max_deg: float = 90.0,
    boundary_small_sector_deg: float = 67.5,
) -> float:
    p = g.vertices[v_idx]
    dirs = _incident_dir_indices(g, v_idx)
    lim = max_deg * pi / 180.0
    unit = pi / 8.0

    # On boundary vertices, exclude outside-paper sectors and evaluate only
    # sectors inside the boundary interval.
    interval_idx = _boundary_interval_idx(p, eps=g.eps)
    if interval_idx is not None:
        s, e = interval_idx
        sec_steps = _sector_steps_boundary(dirs, s, e)
        if not sec_steps:
            return 0.0
        secs = [st * unit for st in sec_steps]
        return sum(max(0.0, sec - lim) for sec in secs)

    if len(dirs) < 2:
        # Interior point with underspecified local crease directions.
        return 10.0
    secs = [st * unit for st in _sector_steps_cyclic(dirs)]
    return sum(max(0.0, sec - lim) for sec in secs)


def _kawasaki_residual_from_dirs(sorted_dirs: Sequence[int]) -> float:
    n = len(sorted_dirs)
    if n < 4 or n % 2 != 0:
        return float("inf")
    sec_steps = _sector_steps_cyclic(sorted_dirs)
    # On 16-direction grid, Kawasaki target is exactly 180deg = 8 steps
    # for each alternating sum.
    target = ANGLE_COUNT // 2
    odd_steps = sum(sec_steps[::2])
    even_steps = sum(sec_steps[1::2])
    return float(abs(odd_steps - target) + abs(even_steps - target)) * (pi / 8.0)


def corner_kawasaki_error(g: CreaseGraphExact, v_idx: int) -> float:
    dirs = _incident_dir_indices(g, v_idx)
    return _kawasaki_residual_from_dirs(dirs)


def _coface_penalty(g: CreaseGraphExact, corner_ids: Sequence[int]) -> int:
    """
    Approximate 'same face' penalty by connected components on the edge graph:
    if corner vertices remain in the same graph component, penalize pair count.
    """
    # Build adjacency.
    adj: Dict[int, Set[int]] = {i: set() for i in range(len(g.vertices))}
    for i, j in g.edges:
        adj[i].add(j)
        adj[j].add(i)

    comp_id: Dict[int, int] = {}
    cid = 0
    for v in range(len(g.vertices)):
        if v in comp_id:
            continue
        stack = [v]
        comp_id[v] = cid
        while stack:
            u = stack.pop()
            for w in adj[u]:
                if w in comp_id:
                    continue
                comp_id[w] = cid
                stack.append(w)
        cid += 1

    pen = 0
    c = list(corner_ids)
    for i in range(len(c)):
        for j in range(i + 1, len(c)):
            if comp_id.get(c[i], -1) == comp_id.get(c[j], -2):
                pen += 1
    return pen


def _kawasaki_target_vertex_ids(g: CreaseGraphExact) -> List[int]:
    """
    Vertices to enforce Kawasaki on.
    Excludes boundary vertices (including the fixed paper corners).
    """
    out: List[int] = []
    for i, p in enumerate(g.vertices):
        if _is_boundary_point(p, tol=1e-8):
            continue
        out.append(i)
    return out


def global_score(
    g: CreaseGraphExact,
    corner_ids: Sequence[int],
    corner_max_deg: float = 90.0,
) -> Tuple[int, float, float, int]:
    """
    Lexicographic score (smaller is better):
    1) number of all (non-paper-corner) vertices violating Kawasaki,
    2) total corner-condition error,
    3) total Kawasaki residual at all (non-paper-corner) vertices.
    4) approximate same-face penalty among corners.
    """
    bad_k = 0
    total_k = 0.0
    total_corner = 0.0
    for v in _kawasaki_target_vertex_ids(g):
        ke = corner_kawasaki_error(g, v)
        total_k += 1000.0 if ke == float("inf") else ke
        if ke > 1e-8:
            bad_k += 1
    for v in corner_ids:
        total_corner += corner_condition_error(g, v, max_deg=corner_max_deg)
    return (bad_k, total_corner, total_k, _coface_penalty(g, corner_ids))


def graph_state_key_exact(g: CreaseGraphExact) -> Tuple:
    coords = tuple((v.x.a, v.x.b, v.y.a, v.y.b) for v in g.vertices)
    edge_coords = []
    for i, j in g.edges:
        a = coords[i]
        b = coords[j]
        edge_coords.append((a, b) if a <= b else (b, a))
    edge_coords.sort()
    return tuple(edge_coords)


def _is_aligned_with_16_dirs(p: PointE, q: PointE) -> bool:
    dx = q.x - p.x
    dy = q.y - p.y
    if dx == ZERO and dy == ZERO:
        return False
    for rx, ry in DIRS:
        if cross(dx, dy, rx, ry) == ZERO:
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


def _crosses_existing_edges(g: CreaseGraphExact, i: int, j: int) -> bool:
    ai = g.vertices[i].approx()
    bj = g.vertices[j].approx()
    for u, v in g.edges:
        if u in (i, j) or v in (i, j):
            continue
        pu = g.vertices[u].approx()
        pv = g.vertices[v].approx()
        if _strict_segments_intersect(ai, bj, pu, pv):
            return True
    return False


def seed_direct_corner_connections(g: CreaseGraphExact, corner_ids: Sequence[int]) -> None:
    """
    Add direct initial edges between corner vertices when:
    - the segment direction is one of the 16 allowed directions, and
    - adding the segment does not strictly cross existing edges.
    """
    ids = list(corner_ids)
    for i, j in combinations(ids, 2):
        if g.has_edge(i, j):
            continue
        p = g.vertices[i]
        q = g.vertices[j]
        if not _is_aligned_with_16_dirs(p, q):
            continue
        if _crosses_existing_edges(g, i, j):
            continue
        g.add_edge(i, j)


def _find_corner_vertex_id(
    g: CreaseGraphExact, corner_ids: Sequence[int], p: PointE, tol: float = 1e-8
) -> Optional[int]:
    for v in corner_ids:
        q = g.vertices[v]
        qx, qy = q.approx()
        px, py = p.approx()
        if abs(qx - px) <= tol and abs(qy - py) <= tol:
            return v
    return None


def _crosses_existing_edges_points(
    g: CreaseGraphExact,
    a: PointE,
    b: PointE,
    ignore_vertex_ids: Sequence[int],
) -> bool:
    ai = a.approx()
    bj = b.approx()
    ignore = set(ignore_vertex_ids)
    for u, v in g.edges:
        if u in ignore or v in ignore:
            continue
        pu = g.vertices[u].approx()
        pv = g.vertices[v].approx()
        if _strict_segments_intersect(ai, bj, pu, pv):
            return True
    return False


def _build_faces(g: CreaseGraphExact) -> Tuple[List[List[int]], Dict[int, Set[int]]]:
    """
    Build planar faces via half-edge traversal.
    Returns:
    - interior face vertex-cycles (outer face removed),
    - vertex -> set(face_id) map for those interior faces.
    """
    nbrs: Dict[int, List[int]] = {i: [] for i in range(len(g.vertices))}
    for i, j in g.edges:
        nbrs[i].append(j)
        nbrs[j].append(i)

    # CCW order around each vertex (float only for local cyclic ordering).
    for v, arr in nbrs.items():
        vx, vy = g.vertices[v].approx()
        arr.sort(key=lambda u: atan2(g.vertices[u].approx()[1] - vy, g.vertices[u].approx()[0] - vx))

    visited: Set[Tuple[int, int]] = set()
    raw_faces: List[List[int]] = []

    for u, v in list((a, b) for a, b in g.edges) + list((b, a) for a, b in g.edges):
        if (u, v) in visited:
            continue
        face: List[int] = []
        cur_u, cur_v = u, v
        guard = 0
        while True:
            guard += 1
            if guard > max(8 * len(g.edges), 64):
                face = []
                break
            visited.add((cur_u, cur_v))
            face.append(cur_u)

            arr = nbrs.get(cur_v, [])
            if not arr:
                face = []
                break
            # Next edge that keeps current face on the left.
            try:
                k = arr.index(cur_u)
            except ValueError:
                face = []
                break
            nxt = arr[(k - 1) % len(arr)]
            cur_u, cur_v = cur_v, nxt
            if (cur_u, cur_v) == (u, v):
                break

        if len(face) >= 3:
            raw_faces.append(face)

    def signed_area(poly: List[int]) -> float:
        pts = [g.vertices[v].approx() for v in poly]
        s = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            s += x1 * y2 - x2 * y1
        return 0.5 * s

    # Remove duplicate cycles by canonical key.
    uniq: Dict[Tuple[int, ...], List[int]] = {}
    for f in raw_faces:
        m = min(f)
        k = f.index(m)
        rot = f[k:] + f[:k]
        rrot = list(reversed(rot))
        key = tuple(rot) if tuple(rot) <= tuple(rrot) else tuple(rrot)
        uniq[key] = f
    faces = list(uniq.values())
    if not faces:
        return [], {}

    areas = [signed_area(f) for f in faces]
    # Outer face is typically the only one with negative area in this traversal.
    outer_ids = {i for i, a in enumerate(areas) if a < 0.0}
    if not outer_ids:
        # Fallback: treat largest-area face as outer.
        outer_ids = {max(range(len(faces)), key=lambda i: abs(areas[i]))}

    interior_faces: List[List[int]] = []
    v2f: Dict[int, Set[int]] = {i: set() for i in range(len(g.vertices))}
    for i, f in enumerate(faces):
        if i in outer_ids:
            continue
        nid = len(interior_faces)
        interior_faces.append(f)
        for v in set(f):
            v2f[v].add(nid)
    return interior_faces, v2f


def _share_interior_face(g: CreaseGraphExact, a_idx: int, b_idx: int) -> bool:
    _, v2f = _build_faces(g)
    return len(v2f.get(a_idx, set()).intersection(v2f.get(b_idx, set()))) > 0


def _best_two_segment_bend(
    g: CreaseGraphExact,
    a_idx: int,
    b_idx: int,
) -> Optional[PointE]:
    """
    Find shortest 2-segment path A-I-B with each segment on 16-direction lines.
    """
    a = g.vertices[a_idx]
    b = g.vertices[b_idx]
    # Require exact co-face relation on current planar subdivision.
    if not _share_interior_face(g, a_idx, b_idx):
        return None

    best_len = float("inf")
    best_i: Optional[PointE] = None
    for da in range(ANGLE_COUNT):
        la = make_line_through_point_dir(a, da)
        for db in range(ANGLE_COUNT):
            lb = make_line_through_point_dir(b, db)
            p = line_intersection(la, lb)
            if p is None or not in_square(p):
                continue
            # Degenerate bends are not useful here.
            if pt_key(p) == pt_key(a) or pt_key(p) == pt_key(b):
                continue
            if _crosses_existing_edges_points(g, a, p, ignore_vertex_ids=[a_idx]):
                continue
            if _crosses_existing_edges_points(g, p, b, ignore_vertex_ids=[b_idx]):
                continue

            ax, ay = a.approx()
            bx, by = b.approx()
            px, py = p.approx()
            plen = ((ax - px) ** 2 + (ay - py) ** 2) ** 0.5 + ((bx - px) ** 2 + (by - py) ** 2) ** 0.5
            if plen < best_len:
                best_len = plen
                best_i = p
    return best_i


def seed_face_shortcuts(g: CreaseGraphExact, corner_ids: Sequence[int]) -> None:
    """
    Generic initial 2-segment shortcuts:
    - for each corner pair not directly connected,
    - if they share the same interior face on the current planar subdivision,
    - add shortest A-I-B shortcut where A-I and I-B are on 16 directions and
      do not strictly cross existing edges.
    """
    ids = list(corner_ids)
    for a_idx, b_idx in combinations(ids, 2):
        if g.has_edge(a_idx, b_idx):
            continue
        bend = _best_two_segment_bend(g, a_idx, b_idx)
        if bend is None:
            continue
        i_idx = g.add_vertex(bend)
        g.add_edge(a_idx, i_idx)
        g.add_edge(i_idx, b_idx)


def beam_search_exact(
    start: CreaseGraphExact,
    corner_ids: Sequence[int],
    enforce_symmetry: bool,
    seed: int,
    max_steps: int,
    beam_width: int,
    branch_per_state: int,
    target_limit: int = 6,
    dir_limit: int = 12,
    score_tol: float = 1e-10,
    greedy_first: bool = True,
    corner_max_deg: float = 90.0,
    enable_tsumami: bool = True,
    enable_open_sink: bool = True,
    enable_triangle_macro: bool = False,
    repair_max_bounces: int = 8,
    randomize_order: bool = True,
    search_mode: str = "beam",
    k_max: Optional[int] = None,
    time_budget_sec: Optional[float] = None,
    debug_log: bool = False,
) -> CreaseGraphExact:
    rng = Random(seed)
    def _maybe_shuffle(seq: List) -> None:
        if randomize_order:
            rng.shuffle(seq)

    def _make_targets(state: CreaseGraphExact) -> Tuple[List[Tuple[int, str]], Set[int]]:
        # 1) prioritize violating corner vertices (larger error first),
        # 2) then Kawasaki-violating targets,
        # 3) fallback to corners.
        violating_corner_sorted = sorted(
            [v for v in corner_ids if corner_condition_error(state, v, max_deg=corner_max_deg) > 1e-8],
            key=lambda v: corner_condition_error(state, v, max_deg=corner_max_deg),
            reverse=True,
        )
        violating_k = [
            v for v in _kawasaki_target_vertex_ids(state) if corner_kawasaki_error(state, v) > 1e-8
        ]
        if violating_corner_sorted:
            base_targets = list(violating_corner_sorted)
            for v in violating_k:
                if v not in base_targets:
                    base_targets.append(v)
        elif violating_k:
            base_targets = violating_k
        else:
            base_targets = list(corner_ids)
            _maybe_shuffle(base_targets)
        base_targets = base_targets[: min(max(1, target_limit), len(base_targets))]

        # When corner violations exist, focus hard on them (disable extra open targets).
        targets: List[Tuple[int, str]] = [(v, "normal") for v in base_targets]
        if not violating_corner_sorted:
            complete_vertices: List[int] = []
            k_targets = set(_kawasaki_target_vertex_ids(state))
            for v in range(len(state.vertices)):
                if corner_condition_error(state, v, max_deg=corner_max_deg) > 1e-8:
                    continue
                if v in k_targets and corner_kawasaki_error(state, v) > 1e-8:
                    continue
                complete_vertices.append(v)
            _maybe_shuffle(complete_vertices)
            for v in complete_vertices[:2]:
                if all(tv != v for tv, _ in targets):
                    targets.append((v, "open_only"))
        return targets, set(violating_corner_sorted)

    best = clone_graph(start)
    best_score = global_score(best, corner_ids, corner_max_deg=corner_max_deg)
    frontier: List[CreaseGraphExact] = [clone_graph(start)]
    visited: Set[Tuple] = {graph_state_key_exact(start)}
    t0 = time.time()

    def _ordered_children_for_state(
        state: CreaseGraphExact,
        base_score: Tuple[int, float, float, int],
        limit: Optional[int] = None,
    ) -> List[Tuple[Tuple[float, float, float, int], CreaseGraphExact]]:
        targets, violating_corner_set = _make_targets(state)

        local_children: List[Tuple[Tuple[float, float, float, int], CreaseGraphExact]] = []
        for v, tmode in targets:
            dirs = admissible_dirs_for_vertex(state, v, enforce_symmetry=enforce_symmetry)
            if not dirs:
                continue
            dirs = sorted(dirs)
            if len(dirs) > max(1, dir_limit):
                head = dirs[: max(1, dir_limit // 2)]
                tail = dirs[max(1, dir_limit // 2) :]
                _maybe_shuffle(tail)
                dirs = head + tail[: (max(1, dir_limit) - len(head))]
            for d in dirs:
                if tmode == "open_only":
                    ops = ["open"] if enable_open_sink else []
                else:
                    ops: List[str] = []
                    if enable_open_sink:
                        ops.append("open")
                    if enable_tsumami:
                        ops.extend(["tsu_short", "tsu_long"])
                _maybe_shuffle(ops)
                if not ops:
                    continue
                for op in ops:
                    if op == "open":
                        hs = [
                            apply_open_sink_action(
                                state,
                                v,
                                d,
                                enforce_symmetry=enforce_symmetry,
                                max_bounces=repair_max_bounces,
                            )
                        ]
                    elif op == "tsu_short":
                        hs = apply_tsumami_action_variants(
                            state,
                            v,
                            d,
                            enforce_symmetry=enforce_symmetry,
                            max_bounces=repair_max_bounces,
                            delete_shorter_side=True,
                        )
                    else:
                        hs = apply_tsumami_action_variants(
                            state,
                            v,
                            d,
                            enforce_symmetry=enforce_symmetry,
                            max_bounces=repair_max_bounces,
                            delete_shorter_side=False,
                        )
                    for h in hs:
                        if h is None:
                            continue
                        key = graph_state_key_exact(h)
                        if key in visited:
                            continue
                        sc = global_score(h, corner_ids, corner_max_deg=corner_max_deg)
                        if sc <= base_score:
                            local_children.append((sc, h))
            # Try triangle macro after open-sink-first expansion.
            if enable_triangle_macro and tmode != "open_only":
                tri_children = apply_triangle_macro_variants(
                    state,
                    anchor_v=v,
                    enforce_symmetry=enforce_symmetry,
                    max_bounces=repair_max_bounces,
                    max_other_vertices=8,
                    corner_max_deg=corner_max_deg,
                )
                for h in tri_children:
                    key = graph_state_key_exact(h)
                    if key in visited:
                        continue
                    sc = global_score(h, corner_ids, corner_max_deg=corner_max_deg)
                    if sc <= base_score:
                        local_children.append((sc, h))
        local_children.sort(key=lambda x: x[0])
        if limit is None:
            return local_children
        return local_children[: max(1, limit)]

    if search_mode == "dfs":
        # Depth-first search with backtracking over non-worsening moves.
        root = clone_graph(start)
        stack: List[Tuple[CreaseGraphExact, int, Optional[List[Tuple[Tuple[float, float, float, int], CreaseGraphExact]]], int]] = [
            (root, 0, None, 0)
        ]
        while stack:
            if time_budget_sec is not None and (time.time() - t0) >= time_budget_sec:
                return best
            state, depth, children, idx = stack[-1]
            sc_state = global_score(state, corner_ids, corner_max_deg=corner_max_deg)
            if sc_state <= best_score:
                best_score = sc_state
                best = clone_graph(state)
            if best_score[0] <= score_tol and best_score[1] <= score_tol:
                return best
            if depth >= max_steps:
                stack.pop()
                continue
            if children is None:
                children = _ordered_children_for_state(state, sc_state, limit=branch_per_state)
                stack[-1] = (state, depth, children, 0)
                idx = 0
            if idx >= len(children):
                stack.pop()
                continue
            ch_sc, ch = children[idx]
            stack[-1] = (state, depth, children, idx + 1)
            key = graph_state_key_exact(ch)
            if key in visited:
                continue
            visited.add(key)
            stack.append((ch, depth + 1, None, 0))
        return best

    for step_idx in range(max_steps):
        if time_budget_sec is not None and (time.time() - t0) >= time_budget_sec:
            if debug_log:
                print(f"[debug] stop_by_time_budget step={step_idx} best_score={best_score}")
            break
        scored_frontier = [
            (global_score(s, corner_ids, corner_max_deg=corner_max_deg), s) for s in frontier
        ]
        scored_frontier.sort(key=lambda x: x[0])
        if scored_frontier[0][0] <= best_score:
            best_score = scored_frontier[0][0]
            best = clone_graph(scored_frontier[0][1])
        # Early stop only when both:
        # - all target vertices satisfy Kawasaki
        # - corner-condition error is also cleared
        if best_score[0] <= score_tol and best_score[1] <= score_tol:
            return best

        next_states: List[Tuple[Tuple[float, float, float, int], CreaseGraphExact]] = []

        if greedy_first:
            # First-improvement greedy:
            # try candidates in seed-driven order, accept the first strict improvement,
            # then immediately advance to next depth.
            base_score, state = scored_frontier[0]
            targets, violating_corner_set = _make_targets(state)

            accepted_child: Optional[CreaseGraphExact] = None
            accepted_score: Optional[Tuple[int, float, float, int]] = None
            step_stats: Dict[str, int] = {}

            def _bump(name: str, delta: int = 1) -> None:
                step_stats[name] = step_stats.get(name, 0) + delta

            _bump("targets", len(targets))
            for v, tmode in targets:
                dirs = admissible_dirs_for_vertex(state, v, enforce_symmetry=enforce_symmetry)
                if not dirs:
                    _bump("reject_no_dirs")
                    continue
                dirs = sorted(dirs)
                _maybe_shuffle(dirs)
                if len(dirs) > max(1, dir_limit):
                    _bump("dirs_trimmed", len(dirs) - max(1, dir_limit))
                    dirs = dirs[: max(1, dir_limit)]
                for d in dirs:
                    _bump("dirs_tested")
                    if tmode == "open_only":
                        ops = ["open"] if enable_open_sink else []
                    else:
                        ops: List[str] = []
                        if enable_open_sink:
                            ops.append("open")
                        if enable_tsumami:
                            ops.extend(["tsu_short", "tsu_long"])
                    _maybe_shuffle(ops)
                    if not ops:
                        _bump("reject_no_ops")
                        continue
                    for op in ops:
                        _bump("ops_tested")
                        if op == "open":
                            hs = [
                                apply_open_sink_action(
                                state,
                                v,
                                d,
                                enforce_symmetry=enforce_symmetry,
                                max_bounces=repair_max_bounces,
                            )
                            ]
                        elif op == "tsu_short":
                            hs = apply_tsumami_action_variants(
                                state,
                                v,
                                d,
                                enforce_symmetry=enforce_symmetry,
                                max_bounces=repair_max_bounces,
                                delete_shorter_side=True,
                            )
                        else:
                            hs = apply_tsumami_action_variants(
                                state,
                                v,
                                d,
                                enforce_symmetry=enforce_symmetry,
                                max_bounces=repair_max_bounces,
                                delete_shorter_side=False,
                            )
                        for h in hs:
                            if h is None:
                                _bump("reject_action_none")
                                continue
                            if not _graph_within_k(h, k_max):
                                _bump("reject_kmax")
                                continue
                            key = graph_state_key_exact(h)
                            if key in visited:
                                _bump("reject_visited")
                                continue
                            sc = global_score(h, corner_ids, corner_max_deg=corner_max_deg)
                            # Relax strict-improvement rule:
                            # allow non-worsening transitions to keep progressing.
                            if sc <= base_score:
                                _bump("accept")
                                accepted_child = h
                                accepted_score = sc
                                break
                            _bump("reject_score")
                        if accepted_child is not None:
                            break
                    if accepted_child is not None:
                        break
                if accepted_child is not None:
                    break
                if enable_triangle_macro and tmode != "open_only":
                    tri_children = apply_triangle_macro_variants(
                        state,
                        anchor_v=v,
                        enforce_symmetry=enforce_symmetry,
                        max_bounces=repair_max_bounces,
                        max_other_vertices=8,
                        corner_max_deg=corner_max_deg,
                    )
                    _bump("tri_candidates", len(tri_children))
                    for h in tri_children:
                        if not _graph_within_k(h, k_max):
                            _bump("tri_reject_kmax")
                            continue
                        key = graph_state_key_exact(h)
                        if key in visited:
                            _bump("tri_reject_visited")
                            continue
                        sc = global_score(h, corner_ids, corner_max_deg=corner_max_deg)
                        if sc <= base_score:
                            _bump("tri_accept")
                            accepted_child = h
                            accepted_score = sc
                            break
                        _bump("tri_reject_score")
                    if accepted_child is not None:
                        break

            if accepted_child is None or accepted_score is None:
                if debug_log:
                    print(
                        "[debug] greedy_no_accept "
                        f"step={step_idx} base_score={base_score} stats={step_stats}"
                    )
                break
            key = graph_state_key_exact(accepted_child)
            visited.add(key)
            frontier = [accepted_child]
            if accepted_score <= best_score:
                best_score = accepted_score
                best = clone_graph(accepted_child)
            if debug_log:
                print(
                    "[debug] greedy_accept "
                    f"step={step_idx} accepted_score={accepted_score} best_score={best_score} stats={step_stats}"
                )
            continue

        for base_score, state in scored_frontier:
            # Priority:
            # 1) corner vertices still violating corner-condition (user-facing primary target),
            # 2) other vertices violating Kawasaki,
            # 3) fallback to corners.
            violating_corner = [
                v for v in corner_ids if corner_condition_error(state, v, max_deg=corner_max_deg) > 1e-8
            ]
            violating_k = [
                v for v in _kawasaki_target_vertex_ids(state) if corner_kawasaki_error(state, v) > 1e-8
            ]
            if violating_corner:
                base_targets = list(violating_corner)
                for v in violating_k:
                    if v not in base_targets:
                        base_targets.append(v)
            elif violating_k:
                base_targets = violating_k
            else:
                base_targets = list(corner_ids)
            _maybe_shuffle(base_targets)
            base_targets = base_targets[: min(max(1, target_limit), len(base_targets))]

            complete_vertices: List[int] = []
            k_targets = set(_kawasaki_target_vertex_ids(state))
            for v in range(len(state.vertices)):
                if corner_condition_error(state, v, max_deg=corner_max_deg) > 1e-8:
                    continue
                if v in k_targets and corner_kawasaki_error(state, v) > 1e-8:
                    continue
                complete_vertices.append(v)
            _maybe_shuffle(complete_vertices)
            extra_open_targets = complete_vertices[:2]
            targets: List[Tuple[int, str]] = [(v, "normal") for v in base_targets]
            for v in extra_open_targets:
                if all(tv != v for tv, _ in targets):
                    targets.append((v, "open_only"))

            local_children: List[Tuple[Tuple[float, float, float, int], CreaseGraphExact]] = []
            for v, tmode in targets:
                if enable_triangle_macro:
                    tri_children = apply_triangle_macro_variants(
                        state,
                        anchor_v=v,
                        enforce_symmetry=enforce_symmetry,
                        max_bounces=repair_max_bounces,
                        max_other_vertices=8,
                        corner_max_deg=corner_max_deg,
                    )
                for h in tri_children:
                    if not _graph_within_k(h, k_max):
                        continue
                    key = graph_state_key_exact(h)
                    if key in visited:
                        continue
                        sc = global_score(h, corner_ids, corner_max_deg=corner_max_deg)
                        if sc[0] > base_score[0]:
                            continue
                        local_children.append((sc, h))
                dirs = admissible_dirs_for_vertex(state, v, enforce_symmetry=enforce_symmetry)
                if not dirs:
                    continue
                # Keep some exploration, but avoid dropping good directions too aggressively.
                # First evaluate all admissible directions in stable order, then optionally
                # subsample only when the set is very large.
                dirs = sorted(dirs)
                if len(dirs) > max(1, dir_limit):
                    head = dirs[: max(1, dir_limit // 2)]
                    tail = dirs[max(1, dir_limit // 2) :]
                    _maybe_shuffle(tail)
                    dirs = head + tail[: (max(1, dir_limit) - len(head))]
                for d in dirs:
                    if tmode == "open_only":
                        ops = ["open"] if enable_open_sink else []
                    else:
                        ops: List[str] = []
                        if enable_open_sink:
                            ops.append("open")
                        if enable_tsumami:
                            ops.extend(["tsu_short", "tsu_long"])
                    _maybe_shuffle(ops)
                    if not ops:
                        continue
                    for op in ops:
                        if op == "open":
                            hs = [
                                apply_open_sink_action(
                                state,
                                v,
                                d,
                                enforce_symmetry=enforce_symmetry,
                                max_bounces=repair_max_bounces,
                            )
                            ]
                        elif op == "tsu_short":
                            hs = apply_tsumami_action_variants(
                                state,
                                v,
                                d,
                                enforce_symmetry=enforce_symmetry,
                                max_bounces=repair_max_bounces,
                                delete_shorter_side=True,
                            )
                        else:
                            hs = apply_tsumami_action_variants(
                                state,
                                v,
                                d,
                                enforce_symmetry=enforce_symmetry,
                                max_bounces=repair_max_bounces,
                                delete_shorter_side=False,
                            )
                        for h in hs:
                            if h is None:
                                continue
                            if not _graph_within_k(h, k_max):
                                continue
                            key = graph_state_key_exact(h)
                            if key in visited:
                                continue
                            sc = global_score(h, corner_ids, corner_max_deg=corner_max_deg)
                            if sc[0] > base_score[0]:
                                continue
                            local_children.append((sc, h))
            local_children.sort(key=lambda x: x[0])
            for sc, h in local_children[:branch_per_state]:
                key = graph_state_key_exact(h)
                if key in visited:
                    continue
                visited.add(key)
                next_states.append((sc, h))
        if not next_states:
            if debug_log:
                print(f"[debug] beam_no_next_states step={step_idx} best_score={best_score}")
            break
        next_states.sort(key=lambda x: x[0])
        frontier = [h for _, h in next_states[:beam_width]]
    return best


def build_pattern_exact(
    corners: Sequence[PointE],
    enforce_symmetry: bool = True,
    seed: int = 0,
    max_steps: int = 120,
    beam_width: int = 24,
    branch_per_state: int = 12,
    target_limit: int = 6,
    dir_limit: int = 12,
    score_tol: float = 1e-10,
    greedy_first: bool = True,
    corner_max_deg: float = 90.0,
    enable_tsumami: bool = True,
    enable_open_sink: bool = True,
    enable_triangle_macro: bool = False,
    repair_max_bounces: int = 8,
    randomize_order: bool = True,
    search_mode: str = "beam",
    staged_k_relax: bool = True,
    k_start: int = 2,
    k_end: int = 4,
    time_budget_sec: Optional[float] = None,
    debug_log: bool = False,
) -> Tuple[CreaseGraphExact, List[int]]:
    g = CreaseGraphExact()
    g.init_square_boundary()
    # Seed diagonal y=x.
    v00 = g.add_vertex(PointE(ZERO, ZERO))
    v11 = g.add_vertex(PointE(ONE, ONE))
    g.add_edge(v00, v11)
    corner_ids = [g.add_vertex(p) for p in corners]
    # Seed direct corner-to-corner connections on the 16-direction grid.
    seed_direct_corner_connections(g, corner_ids)
    # Seed requested face shortcut(s), e.g. (1/sqrt(2),0) <-> (1,1) via one bend.
    seed_face_shortcuts(g, corner_ids)
    if staged_k_relax:
        cur = g
        best = clone_graph(g)
        best_sc = global_score(best, corner_ids, corner_max_deg=corner_max_deg)
        for kmax in range(k_start, k_end + 1):
            cur = beam_search_exact(
                cur,
                corner_ids=corner_ids,
                enforce_symmetry=enforce_symmetry,
                seed=seed,
                max_steps=max_steps,
                beam_width=beam_width,
                branch_per_state=branch_per_state,
                target_limit=target_limit,
                dir_limit=dir_limit,
                score_tol=score_tol,
                greedy_first=greedy_first,
                corner_max_deg=corner_max_deg,
                enable_tsumami=enable_tsumami,
                enable_open_sink=enable_open_sink,
                enable_triangle_macro=enable_triangle_macro,
                repair_max_bounces=repair_max_bounces,
                randomize_order=randomize_order,
                search_mode=search_mode,
                k_max=kmax,
                time_budget_sec=time_budget_sec,
                debug_log=debug_log,
            )
            sc = global_score(cur, corner_ids, corner_max_deg=corner_max_deg)
            if sc <= best_sc:
                best_sc = sc
                best = clone_graph(cur)
            if best_sc[0] <= score_tol and best_sc[1] <= score_tol:
                break
    else:
        best = beam_search_exact(
            g,
            corner_ids=corner_ids,
            enforce_symmetry=enforce_symmetry,
            seed=seed,
            max_steps=max_steps,
            beam_width=beam_width,
            branch_per_state=branch_per_state,
            target_limit=target_limit,
            dir_limit=dir_limit,
            score_tol=score_tol,
            greedy_first=greedy_first,
            corner_max_deg=corner_max_deg,
            enable_tsumami=enable_tsumami,
            enable_open_sink=enable_open_sink,
            enable_triangle_macro=enable_triangle_macro,
            repair_max_bounces=repair_max_bounces,
            randomize_order=randomize_order,
            search_mode=search_mode,
            time_budget_sec=time_budget_sec,
            debug_log=debug_log,
        )
    return best, corner_ids


def render_pattern_exact(
    g: CreaseGraphExact,
    corners: Sequence[PointE],
    out_path: str = "crease_exact.png",
    show_order: bool = False,
) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm

    fig, ax = plt.subplots(figsize=(6, 6), dpi=140)
    edges = list(g.edges)
    edges.sort(key=lambda e: g.edge_birth.get(e, 10**9))
    if show_order and edges:
        n = max(1, len(edges) - 1)
        cmap = cm.get_cmap("viridis")
        for idx, (i, j) in enumerate(edges):
            x1, y1 = g.vertices[i].approx()
            x2, y2 = g.vertices[j].approx()
            c = cmap(idx / n)
            ax.plot([x1, x2], [y1, y2], color=c, linewidth=1.6)
            ax.text((x1 + x2) * 0.5, (y1 + y2) * 0.5, str(idx), fontsize=6, color=c)
    else:
        for i, j in edges:
            x1, y1 = g.vertices[i].approx()
            x2, y2 = g.vertices[j].approx()
            ax.plot([x1, x2], [y1, y2], color="black", linewidth=1.2)
    if corners:
        cx = [p.approx()[0] for p in corners]
        cy = [p.approx()[1] for p in corners]
        ax.scatter(cx, cy, s=38, color="#e63946", zorder=4, label="corners")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.2)
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main() -> None:
    # sample (exactly representable in Q(sqrt(2)))
    corners = [
        PointE(ZERO, ZERO),
        PointE(ONE, ONE),
        PointE(HALF, HALF),
        PointE(INV_SQRT2, ZERO),
        PointE(ZERO, INV_SQRT2),
        PointE(ONE, INV_SQRT2),
        PointE(INV_SQRT2, ONE),
    ]
    corner_max_deg = 90.0  # try 45.0 or 22.5
    g, corner_ids = build_pattern_exact(
        corners,
        enforce_symmetry=True,
        seed=0,
        max_steps=80,
        corner_max_deg=corner_max_deg,
    )
    print(
        {
            "vertices": len(g.vertices),
            "edges": len(g.edges),
            "corner_max_deg": corner_max_deg,
            "corner_errors": [corner_condition_error(g, v, max_deg=corner_max_deg) for v in corner_ids],
            "score": global_score(g, corner_ids, corner_max_deg=corner_max_deg),
        }
    )
    render_pattern_exact(g, corners, out_path="crease_exact.png", show_order=False)
    render_pattern_exact(g, corners, out_path="crease_exact_order.png", show_order=True)
    print({"out": "crease_exact.png", "out_order": "crease_exact_order.png"})


if __name__ == "__main__":
    main()
