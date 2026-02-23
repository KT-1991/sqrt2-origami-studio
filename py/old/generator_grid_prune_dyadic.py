from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from math import atan2, gcd, pi
from typing import Dict, List, Optional, Sequence, Set, Tuple


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _q2_reduce(a: int, b: int, k: int) -> Tuple[int, int, int]:
    if a == 0 and b == 0:
        return (0, 0, 0)
    while k > 0 and (a & 1) == 0 and (b & 1) == 0:
        a >>= 1
        b >>= 1
        k -= 1
    return (a, b, k)


@dataclass(frozen=True)
class Qsqrt2:
    # Represents (a + b*sqrt(2)) / 2^k with integer a,b.
    a: int
    b: int
    k: int = 0

    def __post_init__(self) -> None:
        if self.k < 0:
            raise ValueError("k must be >= 0")
        a, b, k = _q2_reduce(self.a, self.b, self.k)
        object.__setattr__(self, "a", a)
        object.__setattr__(self, "b", b)
        object.__setattr__(self, "k", k)

    @staticmethod
    def from_int(n: int) -> "Qsqrt2":
        return Qsqrt2(n, 0, 0)

    @staticmethod
    def from_dyadic(num: int, k: int) -> "Qsqrt2":
        return Qsqrt2(num, 0, k)

    @staticmethod
    def from_ratio(num: int, den: int) -> "Qsqrt2":
        if den <= 0:
            raise ValueError("denominator must be positive")
        if not _is_power_of_two(den):
            raise ValueError("non-dyadic rational is not supported")
        return Qsqrt2(num, 0, den.bit_length() - 1)

    def __add__(self, o: "Qsqrt2") -> "Qsqrt2":
        k = max(self.k, o.k)
        a = (self.a << (k - self.k)) + (o.a << (k - o.k))
        b = (self.b << (k - self.k)) + (o.b << (k - o.k))
        return Qsqrt2(a, b, k)

    def __sub__(self, o: "Qsqrt2") -> "Qsqrt2":
        k = max(self.k, o.k)
        a = (self.a << (k - self.k)) - (o.a << (k - o.k))
        b = (self.b << (k - self.k)) - (o.b << (k - o.k))
        return Qsqrt2(a, b, k)

    def __mul__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(
            self.a * o.a + 2 * self.b * o.b,
            self.a * o.b + self.b * o.a,
            self.k + o.k,
        )

    def __neg__(self) -> "Qsqrt2":
        return Qsqrt2(-self.a, -self.b, self.k)

    def __truediv__(self, o: "Qsqrt2") -> "Qsqrt2":
        return _q2_div_int_to_q2(_q2_to_int(self), _q2_to_int(o))

    def approx(self) -> float:
        scale = 2.0 ** (-self.k)
        return (float(self.a) + float(self.b) * (2.0**0.5)) * scale


@dataclass(frozen=True)
class Q2Int:
    # Represents (a + b*sqrt(2)) / 2^k with integer a,b.
    a: int
    b: int
    k: int


ZERO = Qsqrt2.from_int(0)
ONE = Qsqrt2.from_int(1)
HALF = Qsqrt2.from_dyadic(1, 1)
INV_SQRT2 = Qsqrt2(0, 1, 1)
SQRT2_MINUS_ONE = Qsqrt2(-1, 1, 0)
ZERO_I = Q2Int(0, 0, 0)


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
DIRS_UNIT_F: List[Tuple[float, float]] = []
for _rx, _ry in DIRS_F:
    _rn = (_rx * _rx + _ry * _ry) ** 0.5
    if _rn <= 1e-15:
        DIRS_UNIT_F.append((0.0, 0.0))
    else:
        DIRS_UNIT_F.append((_rx / _rn, _ry / _rn))


@lru_cache(maxsize=1 << 15)
def _q2_to_int(z: Qsqrt2) -> Optional[Q2Int]:
    return Q2Int(a=z.a, b=z.b, k=z.k)


DIRS_I: List[Tuple[Q2Int, Q2Int]] = []
for _dx, _dy in DIRS:
    _dxi = _q2_to_int(_dx)
    _dyi = _q2_to_int(_dy)
    if _dxi is None or _dyi is None:
        raise ValueError("direction set must be dyadic")
    DIRS_I.append((_dxi, _dyi))


def _q2_sign_aligned(a: int, b: int) -> int:
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


def _q2_sign(z: Qsqrt2) -> int:
    return _q2_sign_aligned(z.a, z.b)


def _q2_cmp(x: Qsqrt2, y: Qsqrt2) -> int:
    k = max(x.k, y.k)
    ax = x.a << (k - x.k)
    bx = x.b << (k - x.k)
    ay = y.a << (k - y.k)
    by = y.b << (k - y.k)
    return _q2_sign_aligned(ax - ay, bx - by)


def _q2_cmp_int(x: Q2Int, y: Q2Int) -> int:
    k = max(x.k, y.k)
    ax = x.a << (k - x.k)
    bx = x.b << (k - x.k)
    ay = y.a << (k - y.k)
    by = y.b << (k - y.k)
    return _q2_sign_aligned(ax - ay, bx - by)


def _q2_sub_int(x: Q2Int, y: Q2Int) -> Q2Int:
    k = max(x.k, y.k)
    ax = x.a << (k - x.k)
    bx = x.b << (k - x.k)
    ay = y.a << (k - y.k)
    by = y.b << (k - y.k)
    return Q2Int(a=ax - ay, b=bx - by, k=k)


def _q2_neg_int(x: Q2Int) -> Q2Int:
    return Q2Int(a=-x.a, b=-x.b, k=x.k)


def _q2_mul_int(x: Q2Int, y: Q2Int) -> Q2Int:
    return Q2Int(
        a=x.a * y.a + 2 * x.b * y.b,
        b=x.a * y.b + x.b * y.a,
        k=x.k + y.k,
    )


def _q2_cross_int(ax: Q2Int, ay: Q2Int, bx: Q2Int, by: Q2Int) -> Q2Int:
    return _q2_sub_int(_q2_mul_int(ax, by), _q2_mul_int(ay, bx))


def _q2_div_int_to_q2(x: Q2Int, y: Q2Int) -> Qsqrt2:
    den = y.a * y.a - 2 * y.b * y.b
    if den == 0:
        raise ZeroDivisionError("singular Qsqrt2 inverse")
    na = x.a * y.a - 2 * x.b * y.b
    nb = -x.a * y.b + x.b * y.a
    if den < 0:
        den = -den
        na = -na
        nb = -nb
    g = gcd(gcd(abs(na), abs(nb)), den)
    if g > 1:
        na //= g
        nb //= g
        den //= g
    if not _is_power_of_two(den):
        raise ValueError("non-dyadic division result")
    den_k = den.bit_length() - 1
    dk = x.k - y.k
    if dk >= 0:
        return Qsqrt2(na, nb, den_k + dk)
    scale = -dk
    return Qsqrt2(na << scale, nb << scale, den_k)


def _in_square(p: PointE) -> bool:
    return (
        _q2_cmp(p.x, ZERO) >= 0
        and _q2_cmp(p.x, ONE) <= 0
        and _q2_cmp(p.y, ZERO) >= 0
        and _q2_cmp(p.y, ONE) <= 0
    )


def _point_key(p: PointE) -> Tuple[int, int, int, int, int, int]:
    return (p.x.a, p.x.b, p.x.k, p.y.a, p.y.b, p.y.k)


_MASK64 = (1 << 64) - 1


def _splitmix64(x: int) -> int:
    z = (x + 0x9E3779B97F4A7C15) & _MASK64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
    return (z ^ (z >> 31)) & _MASK64


def _edge_hash_pair(i: int, j: int) -> Tuple[int, int]:
    a, b = (i, j) if i < j else (j, i)
    x = ((a & 0xFFFFFFFF) << 32) | (b & 0xFFFFFFFF)
    h1 = _splitmix64(x ^ 0xD6E8FEB86659FD93)
    h2 = _splitmix64(x ^ 0xA5A3564E27F8865B)
    return (h1, h2)


def _point_k_level(p: PointE) -> Optional[int]:
    return max(p.x.k, p.y.k)


def _required_bounds_for_qsqrt2(z: Qsqrt2) -> Optional[Tuple[int, int, int]]:
    return (z.k, abs(z.a), abs(z.b))


def _required_grid_bounds_for_point(p: PointE) -> Optional[Tuple[int, int, int]]:
    bx = _required_bounds_for_qsqrt2(p.x)
    by = _required_bounds_for_qsqrt2(p.y)
    if bx is None or by is None:
        return None
    k = max(bx[0], by[0])
    a_max = max(bx[1], by[1])
    b_max = max(bx[2], by[2])
    return (a_max, b_max, k)


def _record_missing_point_stats(stats: Optional[Dict[str, int]], p: PointE) -> None:
    if stats is None:
        return
    stats["reject_missing_grid_point"] = stats.get("reject_missing_grid_point", 0) + 1
    req = _required_grid_bounds_for_point(p)
    if req is None:
        stats["reject_missing_grid_point_unknown"] = stats.get("reject_missing_grid_point_unknown", 0) + 1
        return
    ra, rb, rk = req
    stats["expand_need_a_max"] = max(stats.get("expand_need_a_max", 0), ra)
    stats["expand_need_b_max"] = max(stats.get("expand_need_b_max", 0), rb)
    stats["expand_need_k_max"] = max(stats.get("expand_need_k_max", 0), rk)


def _cross(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2) -> Qsqrt2:
    return ax * by - ay * bx


def _dot(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2) -> Qsqrt2:
    return ax * bx + ay * by


def _ray_segment_hit_exact(
    origin: PointE,
    d: Tuple[Qsqrt2, Qsqrt2],
    a: PointE,
    b: PointE,
) -> Optional[Tuple[Qsqrt2, int, PointE]]:
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
    if _q2_cmp(u, ZERO) <= 0:
        return (t, -1, a)
    if _q2_cmp(u, ONE) >= 0:
        return (t, 1, b)
    p = PointE(origin.x + t * dx, origin.y + t * dy)
    return (t, 0, p)


def _ray_segment_hit(
    origin: PointE,
    d: Tuple[Qsqrt2, Qsqrt2],
    a: PointE,
    b: PointE,
    origin_i: Optional[Tuple[Q2Int, Q2Int]] = None,
    d_i: Optional[Tuple[Q2Int, Q2Int]] = None,
    a_i: Optional[Tuple[Q2Int, Q2Int]] = None,
    b_i: Optional[Tuple[Q2Int, Q2Int]] = None,
) -> Optional[Tuple[Qsqrt2, int, PointE]]:
    # Dyadic integer fast path.
    if origin_i is None:
        ox = _q2_to_int(origin.x)
        oy = _q2_to_int(origin.y)
    else:
        ox, oy = origin_i
    if a_i is None:
        ax = _q2_to_int(a.x)
        ay = _q2_to_int(a.y)
    else:
        ax, ay = a_i
    if b_i is None:
        bx = _q2_to_int(b.x)
        by = _q2_to_int(b.y)
    else:
        bx, by = b_i
    if d_i is None:
        dx = _q2_to_int(d[0])
        dy = _q2_to_int(d[1])
    else:
        dx, dy = d_i
    if ox is None or oy is None or ax is None or ay is None or bx is None or by is None or dx is None or dy is None:
        return _ray_segment_hit_exact(origin, d, a, b)

    vx = _q2_sub_int(bx, ax)
    vy = _q2_sub_int(by, ay)
    wx = _q2_sub_int(ax, ox)
    wy = _q2_sub_int(ay, oy)

    denom = _q2_cross_int(dx, dy, vx, vy)
    sden = _q2_sign_aligned(denom.a, denom.b)
    if sden == 0:
        return None

    t_num = _q2_cross_int(wx, wy, vx, vy)
    stn = _q2_sign_aligned(t_num.a, t_num.b)
    if stn == 0 or stn != sden:
        return None

    u_num = _q2_cross_int(wx, wy, dx, dy)
    if sden < 0:
        denom = _q2_neg_int(denom)
        t_num = _q2_neg_int(t_num)
        u_num = _q2_neg_int(u_num)

    if _q2_cmp_int(u_num, ZERO_I) < 0 or _q2_cmp_int(u_num, denom) > 0:
        return None

    t = _q2_div_int_to_q2(t_num, denom)
    if _q2_cmp_int(u_num, ZERO_I) == 0:
        return (t, -1, a)
    if _q2_cmp_int(u_num, denom) == 0:
        return (t, 1, b)

    p = PointE(origin.x + t * d[0], origin.y + t * d[1])
    return (t, 0, p)


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


@lru_cache(maxsize=1 << 15)
def _nearest_dir_idx(dx: float, dy: float) -> int:
    if abs(dx) + abs(dy) <= 1e-15:
        return 0
    best_k = 0
    best_dot = -1e100
    for k, (ux, uy) in enumerate(DIRS_UNIT_F):
        dot = dx * ux + dy * uy
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
) -> Tuple[List[PointE], Dict[Tuple[int, int, int, int, int, int], int]]:
    xvals: Dict[Qsqrt2, Qsqrt2] = {}
    for k in range(k_max + 1):
        for a in range(-a_max, a_max + 1):
            for b in range(-b_max, b_max + 1):
                z = Qsqrt2(a, b, k)
                if _q2_cmp(z, ZERO) >= 0 and _q2_cmp(z, ONE) <= 0:
                    xvals[z] = z
    xs = list(xvals.values())
    points: List[PointE] = []
    p2i: Dict[Tuple[int, int, int, int, int, int], int] = {}
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
        p2i: Dict[Tuple[int, int, int, int, int, int], int],
        points_f: Optional[Sequence[Tuple[float, float]]] = None,
        share_base: bool = False,
        use_local_ray_dirty: bool = False,
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
        self.ray_hit: Dict[int, List[Optional[Tuple[int, int, int, PointE]]]] = {}
        self.ray_hit_rev: Dict[Tuple[int, int], Set[int]] = {}
        self.ray_dirty: Set[int] = set()
        self.edge_dir_idx: Dict[Tuple[int, int], Optional[int]] = {}
        self.edge_parallel_buckets: List[Set[Tuple[int, int]]] = [set() for _ in range(ANGLE_COUNT // 2)]
        self.edge_unknown_dir: Set[Tuple[int, int]] = set()
        self.incident_dirs_cache: Dict[int, List[int]] = {}
        self.incident_dirs_dirty: Set[int] = set()
        self.kawasaki_cache: Dict[int, float] = {}
        self.kawasaki_dirty: Set[int] = set()
        self.point_int_cache: Dict[int, Optional[Tuple[Q2Int, Q2Int]]] = {}
        self.mirror_vid_cache: Dict[int, Optional[int]] = {}
        self.state_hash1: int = 0
        self.state_hash2: int = 0
        self.use_local_ray_dirty: bool = use_local_ray_dirty
        self._tx_logs: List[List[Tuple[str, Tuple]]] = []
        self._tx_replaying: bool = False

    def _norm_edge(self, i: int, j: int) -> Tuple[int, int]:
        return (i, j) if i < j else (j, i)

    def _toggle_edge_hash(self, e: Tuple[int, int]) -> None:
        h1, h2 = _edge_hash_pair(e[0], e[1])
        self.state_hash1 = (self.state_hash1 ^ h1) & _MASK64
        self.state_hash2 = (self.state_hash2 ^ h2) & _MASK64

    def _tx_record(self, op: str, *args) -> None:
        if self._tx_logs and not self._tx_replaying:
            self._tx_logs[-1].append((op, args))

    def tx_begin(self) -> None:
        self._tx_logs.append([("SET_EDGE_BIRTH_COUNTER", (self.edge_birth_counter,))])

    def _deactivate_vertex_shallow(self, v: int) -> None:
        if v not in self.active_vertices:
            return
        for u in list(self.adj.get(v, set())):
            self.adj.get(u, set()).discard(v)
        self._clear_ray_hit_row(v)
        self.active_vertices.discard(v)
        self.adj.pop(v, None)
        self.ray_next.pop(v, None)
        self.ray_hit.pop(v, None)
        self.ray_dirty.discard(v)
        self.incident_dirs_cache.pop(v, None)
        self.incident_dirs_dirty.discard(v)
        self.kawasaki_cache.pop(v, None)
        self.kawasaki_dirty.discard(v)

    def _add_edge_raw(self, i: int, j: int, boundary: bool, birth: Optional[int]) -> None:
        if i == j:
            return
        self.activate_vertex(i)
        self.activate_vertex(j)
        e = self._norm_edge(i, j)
        if e in self.edges:
            if boundary:
                self.boundary_edges.add(e)
            return
        self.edges.add(e)
        self._toggle_edge_hash(e)
        if birth is None:
            self.edge_birth[e] = self.edge_birth_counter
            self.edge_birth_counter += 1
        else:
            self.edge_birth[e] = birth
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

    def _remove_edge_raw(self, i: int, j: int) -> None:
        e = self._norm_edge(i, j)
        if e not in self.edges:
            return
        self._toggle_edge_hash(e)
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

    def tx_rollback(self) -> None:
        if not self._tx_logs:
            return
        log = self._tx_logs.pop()
        self._tx_replaying = True
        try:
            for op, args in reversed(log):
                if op == "SET_EDGE_BIRTH_COUNTER":
                    self.edge_birth_counter = args[0]
                elif op == "DEACTIVATE_VERTEX":
                    self._deactivate_vertex_shallow(args[0])
                elif op == "SET_BOUNDARY_FLAG":
                    e, prev = args
                    if prev:
                        self.boundary_edges.add(e)
                    else:
                        self.boundary_edges.discard(e)
                elif op == "REMOVE_EDGE_RAW":
                    self._remove_edge_raw(args[0], args[1])
                elif op == "RESTORE_EDGE_RAW":
                    self._add_edge_raw(args[0], args[1], boundary=bool(args[2]), birth=args[3])
        finally:
            self._tx_replaying = False

    def tx_commit(self) -> None:
        if self._tx_logs:
            self._tx_logs.pop()

    def activate_vertex(self, v: int) -> None:
        if v not in self.active_vertices:
            self._tx_record("DEACTIVATE_VERTEX", v)
        self.active_vertices.add(v)
        self.adj.setdefault(v, set())
        if v not in self.ray_next:
            self.ray_next[v] = [None] * ANGLE_COUNT
        if v not in self.ray_hit:
            self.ray_hit[v] = [None] * ANGLE_COUNT
        self.ray_dirty.add(v)
        self.incident_dirs_dirty.add(v)
        self.kawasaki_dirty.add(v)

    def _mark_local_dirty(self, v: int) -> None:
        self.incident_dirs_dirty.add(v)
        self.kawasaki_dirty.add(v)

    def _clear_ray_hit_row(self, v: int) -> None:
        row = self.ray_hit.get(v)
        if row is None:
            return
        for hit in row:
            if hit is None:
                continue
            e = self._norm_edge(hit[0], hit[1])
            vs = self.ray_hit_rev.get(e)
            if vs is None:
                continue
            vs.discard(v)
            if not vs:
                self.ray_hit_rev.pop(e, None)

    def _point_int_pair(self, v: int) -> Optional[Tuple[Q2Int, Q2Int]]:
        if v in self.point_int_cache:
            return self.point_int_cache[v]
        p = self.points[v]
        xi = _q2_to_int(p.x)
        yi = _q2_to_int(p.y)
        out: Optional[Tuple[Q2Int, Q2Int]]
        if xi is None or yi is None:
            out = None
        else:
            out = (xi, yi)
        self.point_int_cache[v] = out
        return out

    def mirror_vertex_idx(self, v: int) -> Optional[int]:
        if v in self.mirror_vid_cache:
            return self.mirror_vid_cache[v]
        p = self.points[v]
        mv = self.point_to_id.get((p.y.a, p.y.b, p.y.k, p.x.a, p.x.b, p.x.k))
        self.mirror_vid_cache[v] = mv
        return mv

    def _edge_dir_bucket(self, i: int, j: int) -> Optional[int]:
        # Hot path: quantize by float direction; edges are constrained to 16 bins.
        x1, y1 = self.points_f[i]
        x2, y2 = self.points_f[j]
        d = _nearest_dir_idx(x2 - x1, y2 - y1)
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

    def add_edge(self, i: int, j: int, boundary: bool = False, mark_ray_dirty: bool = True) -> None:
        if i == j:
            return
        self.activate_vertex(i)
        self.activate_vertex(j)
        e = self._norm_edge(i, j)
        if e in self.edges:
            if boundary:
                if e not in self.boundary_edges:
                    self._tx_record("SET_BOUNDARY_FLAG", e, False)
                self.boundary_edges.add(e)
            return
        pi = self.points_f[i]
        pj = self.points_f[j]
        b_new = self._edge_dir_bucket(i, j)
        if b_new is None:
            candidates = self.edges
            for u, v in candidates:
                pu = self.points_f[u]
                pv = self.points_f[v]
                if _collinear_overlap_length(pi, pj, pu, pv) > 1e-10:
                    return
        else:
            for u, v in self.edge_parallel_buckets[b_new]:
                pu = self.points_f[u]
                pv = self.points_f[v]
                if _collinear_overlap_length(pi, pj, pu, pv) > 1e-10:
                    return
            for u, v in self.edge_unknown_dir:
                pu = self.points_f[u]
                pv = self.points_f[v]
                if _collinear_overlap_length(pi, pj, pu, pv) > 1e-10:
                    return
        self._tx_record("REMOVE_EDGE_RAW", e[0], e[1])
        self._add_edge_raw(i, j, boundary=boundary, birth=None)
        if mark_ray_dirty:
            self._mark_ray_dirty_after_change([e])

    def remove_edge(self, i: int, j: int, mark_ray_dirty: bool = True) -> None:
        e = self._norm_edge(i, j)
        if e not in self.edges:
            return
        was_boundary = e in self.boundary_edges
        old_birth = self.edge_birth.get(e)
        self._tx_record("RESTORE_EDGE_RAW", e[0], e[1], was_boundary, old_birth)
        self._remove_edge_raw(i, j)
        if mark_ray_dirty:
            self._mark_ray_dirty_after_change([e])

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
        origin_i = self._point_int_pair(v)
        origin_f = self.points_f[v]
        row: List[Optional[int]] = [None] * ANGLE_COUNT
        row_hit: List[Optional[Tuple[int, int, int, PointE]]] = [None] * ANGLE_COUNT
        tol = 1e-9
        for d in range(ANGLE_COUNT):
            d_f = DIRS_F[d]
            d_i = DIRS_I[d]
            best_t_f: Optional[float] = None
            shortlist: List[Tuple[float, int, int]] = []
            for i, j in self._iter_edges_for_ray_dir(d):
                t_f = _ray_segment_hit_t_float(origin_f, d_f, self.points_f[i], self.points_f[j], eps=1e-12)
                if t_f is None:
                    continue
                if best_t_f is None or t_f < best_t_f - tol:
                    best_t_f = t_f
                    shortlist = [(t_f, i, j)]
                elif abs(t_f - best_t_f) <= tol:
                    shortlist.append((t_f, i, j))
            if not shortlist:
                row[d] = None
                row_hit[d] = None
                continue

            best_row_t: Optional[Qsqrt2] = None
            best_hit_idx: Optional[int] = None
            best_t: Optional[Qsqrt2] = None
            best_hit: Optional[Tuple[int, int, int, PointE]] = None
            shortlist.sort(key=lambda x: x[0])
            for _, i, j in shortlist:
                a = self.points[i]
                b = self.points[j]
                hit = _ray_segment_hit(
                    origin,
                    DIRS[d],
                    a,
                    b,
                    origin_i=origin_i,
                    d_i=d_i,
                    a_i=self._point_int_pair(i),
                    b_i=self._point_int_pair(j),
                )
                if hit is None:
                    continue
                t, hit_pos, p = hit
                if best_t is None or _q2_cmp(t, best_t) < 0:
                    best_t = t
                    best_hit = (i, j, hit_pos, p)
                if hit_pos < 0:
                    cand = i
                elif hit_pos > 0:
                    cand = j
                else:
                    key = _point_key(p)
                    cand = self.point_to_id.get(key)
                    if cand is None:
                        continue
                if cand == v:
                    continue
                if best_row_t is None or _q2_cmp(t, best_row_t) < 0:
                    best_row_t = t
                    best_hit_idx = cand
            row[d] = best_hit_idx
            row_hit[d] = best_hit
        self.ray_next[v] = row
        self._clear_ray_hit_row(v)
        self.ray_hit[v] = row_hit
        for hit in row_hit:
            if hit is None:
                continue
            e = self._norm_edge(hit[0], hit[1])
            self.ray_hit_rev.setdefault(e, set()).add(v)
        self.ray_dirty.discard(v)

    def _mark_all_ray_dirty(self) -> None:
        self.ray_dirty.update(self.active_vertices)

    def _mark_ray_dirty_after_change(self, changed_edges: Sequence[Tuple[int, int]]) -> None:
        if self.use_local_ray_dirty:
            self._mark_ray_dirty_by_changed_edges(changed_edges)
        else:
            self._mark_all_ray_dirty()

    def _mark_ray_dirty_by_changed_edges(self, changed_edges: Sequence[Tuple[int, int]]) -> None:
        if not changed_edges:
            return
        changed: Set[Tuple[int, int]] = set()
        for i, j in changed_edges:
            changed.add(self._norm_edge(i, j))

        # Always invalidate local neighborhood around touched edges.
        local_touch: Set[int] = set()
        added_edges: List[Tuple[int, int]] = []
        for i, j in changed:
            local_touch.add(i)
            local_touch.add(j)
            local_touch.update(self.adj.get(i, set()))
            local_touch.update(self.adj.get(j, set()))
            if (i, j) in self.edges:
                added_edges.append((i, j))
        self.ray_dirty.update(v for v in local_touch if v in self.active_vertices)

        # Invalidate rays that were directly hitting changed edges.
        for e in changed:
            self.ray_dirty.update(self.ray_hit_rev.get(e, set()))

        # Conservative blocker check for newly added edges only.
        if not added_edges:
            return
        edge_segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = [
            (self.points_f[i], self.points_f[j]) for i, j in added_edges
        ]
        for v in self.active_vertices:
            if v in self.ray_dirty:
                continue
            origin_f = self.points_f[v]
            hit_any = False
            for d_f in DIRS_F:
                for a_f, b_f in edge_segs:
                    if _ray_segment_hit_t_float(origin_f, d_f, a_f, b_f, eps=1e-12) is not None:
                        self.ray_dirty.add(v)
                        hit_any = True
                        break
                if hit_any:
                    break

    def ensure_ray_next(self, v: int) -> List[Optional[int]]:
        if v not in self.active_vertices:
            self.activate_vertex(v)
        if v in self.ray_dirty:
            self.recompute_ray_next_for_vertex(v)
        return self.ray_next[v]

    def ray_next_at(self, v: int, dir_idx: int) -> Optional[int]:
        return self.ensure_ray_next(v)[dir_idx]

    def ray_hit_at(self, v: int, dir_idx: int) -> Optional[Tuple[int, int, int, PointE]]:
        self.ensure_ray_next(v)
        return self.ray_hit[v][dir_idx]

    def recompute_ray_next_all(self) -> None:
        for v in sorted(self.active_vertices):
            self.recompute_ray_next_for_vertex(v)

    def first_hit_edge(self, origin_v: int, dir_idx: int) -> Optional[Tuple[int, int, int, PointE]]:
        # Fast path: reuse cached exact hit when this vertex is already clean.
        if origin_v in self.active_vertices and origin_v not in self.ray_dirty:
            row = self.ray_hit.get(origin_v)
            if row is not None:
                return row[dir_idx]

        # Fallback: compute only this direction to avoid full 16-dir recompute.
        origin_f = self.points_f[origin_v]
        d_f = DIRS_F[dir_idx]
        d_i = DIRS_I[dir_idx]
        origin = self.points[origin_v]
        origin_i = self._point_int_pair(origin_v)

        best_t_f: Optional[float] = None
        shortlist: List[Tuple[float, int, int]] = []
        tol = 1e-9
        for i, j in self._iter_edges_for_ray_dir(dir_idx):
            t_f = _ray_segment_hit_t_float(origin_f, d_f, self.points_f[i], self.points_f[j])
            if t_f is None:
                continue
            if best_t_f is None or t_f < best_t_f - tol:
                best_t_f = t_f
                shortlist = [(t_f, i, j)]
            elif abs(t_f - best_t_f) <= tol:
                shortlist.append((t_f, i, j))

        if not shortlist:
            return None

        best_t: Optional[Qsqrt2] = None
        best: Optional[Tuple[int, int, int, PointE]] = None
        shortlist.sort(key=lambda x: x[0])
        for _, i, j in shortlist:
            hit = _ray_segment_hit(
                origin,
                DIRS[dir_idx],
                self.points[i],
                self.points[j],
                origin_i=origin_i,
                d_i=d_i,
                a_i=self._point_int_pair(i),
                b_i=self._point_int_pair(j),
            )
            if hit is None:
                continue
            t, hit_pos, p = hit
            if best_t is None or _q2_cmp(t, best_t) < 0:
                best_t = t
                best = (i, j, hit_pos, p)
        return best

    def shoot_ray_and_split(self, origin_v: int, dir_idx: int, stats: Optional[Dict[str, int]] = None) -> Optional[Tuple[int, int]]:
        if origin_v not in self.active_vertices:
            return None
        hit = self.first_hit_edge(origin_v, dir_idx)
        if hit is None:
            return None
        i, j, hit_pos, p = hit
        old_e = self._norm_edge(i, j)
        was_boundary = old_e in self.boundary_edges
        changed_edges: List[Tuple[int, int]] = []
        if hit_pos < 0:
            hit_v = i
        elif hit_pos > 0:
            hit_v = j
        else:
            key = _point_key(p)
            hit_v = self.point_to_id.get(key)
            if hit_v is None:
                _record_missing_point_stats(stats, p)
                return None
            self.activate_vertex(hit_v)
            self.remove_edge(i, j, mark_ray_dirty=False)
            changed_edges.append(old_e)
            self.add_edge(i, hit_v, boundary=was_boundary, mark_ray_dirty=False)
            self.add_edge(hit_v, j, boundary=was_boundary, mark_ray_dirty=False)
            changed_edges.append(self._norm_edge(i, hit_v))
            changed_edges.append(self._norm_edge(hit_v, j))
        self.add_edge(origin_v, hit_v, boundary=False, mark_ray_dirty=False)
        changed_edges.append(self._norm_edge(origin_v, hit_v))
        self._mark_ray_dirty_after_change(changed_edges)
        return (origin_v, hit_v)


def clone_graph(g: GridCreaseGraph) -> GridCreaseGraph:
    h = GridCreaseGraph(
        points=g.points,
        p2i=g.point_to_id,
        points_f=g.points_f,
        share_base=True,
        use_local_ray_dirty=g.use_local_ray_dirty,
    )
    h.active_vertices = set(g.active_vertices)
    h.edges = set(g.edges)
    h.boundary_edges = set(g.boundary_edges)
    h.edge_birth = dict(g.edge_birth)
    h.edge_birth_counter = g.edge_birth_counter
    h.adj = {k: set(vs) for k, vs in g.adj.items()}
    h.ray_next = {k: list(row) for k, row in g.ray_next.items()}
    h.ray_hit = {k: list(row) for k, row in g.ray_hit.items()}
    h.ray_hit_rev = {e: set(vs) for e, vs in g.ray_hit_rev.items()}
    h.ray_dirty = set(g.ray_dirty)
    h.edge_dir_idx = dict(g.edge_dir_idx)
    h.edge_parallel_buckets = [set(es) for es in g.edge_parallel_buckets]
    h.edge_unknown_dir = set(g.edge_unknown_dir)
    h.incident_dirs_cache = {k: list(vs) for k, vs in g.incident_dirs_cache.items()}
    h.incident_dirs_dirty = set(g.incident_dirs_dirty)
    h.kawasaki_cache = dict(g.kawasaki_cache)
    h.kawasaki_dirty = set(g.kawasaki_dirty)
    h.point_int_cache = dict(g.point_int_cache)
    h.mirror_vid_cache = dict(g.mirror_vid_cache)
    h.state_hash1 = g.state_hash1
    h.state_hash2 = g.state_hash2
    return h


def adopt_graph_state(dst: GridCreaseGraph, src: GridCreaseGraph) -> None:
    # Base geometry is immutable and shared; only mutable topology/caches are replaced.
    dst.active_vertices = set(src.active_vertices)
    dst.edges = set(src.edges)
    dst.boundary_edges = set(src.boundary_edges)
    dst.edge_birth = dict(src.edge_birth)
    dst.edge_birth_counter = src.edge_birth_counter
    dst.adj = {k: set(vs) for k, vs in src.adj.items()}
    dst.ray_next = {k: list(row) for k, row in src.ray_next.items()}
    dst.ray_hit = {k: list(row) for k, row in src.ray_hit.items()}
    dst.ray_hit_rev = {e: set(vs) for e, vs in src.ray_hit_rev.items()}
    dst.ray_dirty = set(src.ray_dirty)
    dst.edge_dir_idx = dict(src.edge_dir_idx)
    dst.edge_parallel_buckets = [set(es) for es in src.edge_parallel_buckets]
    dst.edge_unknown_dir = set(src.edge_unknown_dir)
    dst.incident_dirs_cache = {k: list(vs) for k, vs in src.incident_dirs_cache.items()}
    dst.incident_dirs_dirty = set(src.incident_dirs_dirty)
    dst.kawasaki_cache = dict(src.kawasaki_cache)
    dst.kawasaki_dirty = set(src.kawasaki_dirty)
    dst.point_int_cache = dict(src.point_int_cache)
    dst.mirror_vid_cache = dict(src.mirror_vid_cache)
    dst.state_hash1 = src.state_hash1
    dst.state_hash2 = src.state_hash2
    dst.use_local_ray_dirty = src.use_local_ray_dirty


def find_vertex_idx(g: GridCreaseGraph, p: PointE) -> Optional[int]:
    return g.point_to_id.get(_point_key(p))


def _is_boundary_vertex(g: GridCreaseGraph, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    return abs(x) <= tol or abs(x - 1.0) <= tol or abs(y) <= tol or abs(y - 1.0) <= tol


def _is_square_corner_vertex(g: GridCreaseGraph, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    on_x = abs(x) <= tol or abs(x - 1.0) <= tol
    on_y = abs(y) <= tol or abs(y - 1.0) <= tol
    return on_x and on_y


def _on_diag_vertex(g: GridCreaseGraph, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    return abs(x - y) <= tol


def diagonal_symmetry_ok(g: GridCreaseGraph) -> bool:
    for i, j in g.edges:
        mi = g.mirror_vertex_idx(i)
        mj = g.mirror_vertex_idx(j)
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
    # Hot path: use float-direction quantization instead of exact Qsqrt2 delta math.
    # Edges are constrained to 16 directions, so nearest-bin mapping is stable in practice.
    vx, vy = g.points_f[v_idx]
    out: Set[int] = set()
    for u in g.adj.get(v_idx, set()):
        ux, uy = g.points_f[u]
        out.add(_nearest_dir_idx(ux - vx, uy - vy))
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
    h = g
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
    h = g
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
    stats: Optional[Dict[str, int]] = None,
) -> Optional[GridCreaseGraph]:
    h = clone_graph(g)
    if h.shoot_ray_and_split(v_idx, dir_idx, stats=stats) is None:
        return None
    if enforce_symmetry:
        mv = h.mirror_vertex_idx(v_idx)
        if mv is None:
            return None
        md = mirrored_dir_idx(dir_idx)
        if not (mv == v_idx and md == dir_idx):
            if h.shoot_ray_and_split(mv, md, stats=stats) is None:
                return None
        if not diagonal_symmetry_ok(h):
            return None
    return h


def _run_open_sink_transaction(
    g: GridCreaseGraph,
    fronts_init: Sequence[Tuple[int, int]],
    enforce_symmetry: bool = True,
    max_bounces: int = 14,
    stats: Optional[Dict[str, int]] = None,
) -> Optional[GridCreaseGraph]:
    if not fronts_init:
        return None
    h = g
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
            i, j, hit_pos, p_hit = hit
            a_f = h.points_f[i]
            b_f = h.points_f[j]
            hit_interior = hit_pos == 0
            if h.shoot_ray_and_split(cur_v, cur_d, stats=stats) is None:
                return None

            if hit_pos < 0:
                next_v = i
            elif hit_pos > 0:
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
    in_place: bool = False,
    stats: Optional[Dict[str, int]] = None,
) -> Optional[GridCreaseGraph]:
    h0 = g if in_place else clone_graph(g)
    fronts: List[Tuple[int, int]] = [(v_idx, dir_idx)]
    if enforce_symmetry:
        mv = h0.mirror_vertex_idx(v_idx)
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
        stats=stats,
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


def _dir_gap_steps(a: int, b: int) -> int:
    d = abs(a - b) % ANGLE_COUNT
    return min(d, ANGLE_COUNT - d)


def _first_hit_target_key(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
) -> Optional[Tuple]:
    hit_v = g.ray_next_at(v_idx, dir_idx)
    if hit_v is None:
        return None
    return ("V", hit_v)


def _move_equiv_key(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool,
) -> Optional[Tuple]:
    first_key = _first_hit_target_key(g, v_idx, dir_idx)
    if first_key is None:
        return None
    mirror_key: Optional[Tuple] = None
    if enforce_symmetry:
        mv = g.mirror_vertex_idx(v_idx)
        if mv is None:
            mirror_key = ("MISSING_MIRROR_VERTEX",)
        else:
            md = mirrored_dir_idx(dir_idx)
            mirror_key = _first_hit_target_key(g, mv, md)
    return (v_idx, first_key, mirror_key)


def _topk_dirs_for_vertex(
    g: GridCreaseGraph,
    v_idx: int,
    dirs: Sequence[int],
    used_dirs: Set[int],
    k: int,
    first_hit_map: Optional[Dict[int, Optional[int]]] = None,
) -> List[int]:
    if k <= 0 or len(dirs) <= k:
        return list(dirs)
    used_sorted = sorted(used_dirs)
    scored: List[Tuple[float, int, int, int]] = []
    for d in dirs:
        local = sorted(set(used_dirs | {d}))
        ke = _kawasaki_residual_from_dirs(local)
        if first_hit_map is None:
            hit_v = g.ray_next_at(v_idx, d)
        else:
            hit_v = first_hit_map.get(d)
        bpen = 1 if (hit_v is not None and _is_boundary_vertex(g, hit_v)) else 0
        if used_sorted:
            gap = min(_dir_gap_steps(d, ud) for ud in used_sorted)
        else:
            gap = 0
        scored.append((ke, bpen, gap, d))
    scored.sort()
    return [d for _, _, _, d in scored[:k]]


def _edge_dir_from(g: GridCreaseGraph, v_idx: int, u_idx: int) -> Optional[int]:
    e = g._norm_edge(v_idx, u_idx)
    b = g.edge_dir_idx.get(e)
    if b is not None:
        vx, vy = g.points_f[v_idx]
        ux, uy = g.points_f[u_idx]
        dx = ux - vx
        dy = uy - vy
        bx, by = DIRS_F[b]
        if dx * bx + dy * by >= 0.0:
            return b
        return (b + ANGLE_COUNT // 2) % ANGLE_COUNT

    vp = g.points[v_idx]
    up = g.points[u_idx]
    d = _exact_dir_idx_from_delta(up.x - vp.x, up.y - vp.y)
    if d is not None:
        return d
    vx, vy = g.points_f[v_idx]
    ux, uy = g.points_f[u_idx]
    return _nearest_dir_idx(ux - vx, uy - vy)


def _pick_incident_edge_in_dir(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
    deleted: Set[Tuple[int, int]],
) -> Optional[Tuple[int, int, int]]:
    best: Optional[Tuple[float, int, int, int]] = None
    vx, vy = g.points_f[v_idx]
    for u in g.adj.get(v_idx, set()):
        e = g._norm_edge(v_idx, u)
        if e in deleted or e in g.boundary_edges:
            continue
        d = _edge_dir_from(g, v_idx, u)
        if d is None or d != dir_idx:
            continue
        ux, uy = g.points_f[u]
        dist2 = (ux - vx) ** 2 + (uy - vy) ** 2
        cand = (dist2, e[0], e[1], u)
        if best is None or cand < best:
            best = cand
    if best is None:
        return None
    _, i, j, u = best
    return (i, j, u)


def _collect_delete_chain_from_blocker(
    g: GridCreaseGraph,
    blocker: Tuple[int, int],
    max_steps: int = 6,
) -> Set[Tuple[int, int]]:
    deleted: Set[Tuple[int, int]] = {blocker}
    a, b = blocker
    starts: List[Tuple[int, int]] = [(a, b), (b, a)]
    for start_v, other_v in starts:
        incoming_d = _edge_dir_from(g, start_v, other_v)
        if incoming_d is None:
            continue
        cur_v = start_v
        seen_local: Set[Tuple[int, int]] = set()
        for _ in range(max_steps):
            if _is_boundary_vertex(g, cur_v):
                break
            key = (cur_v, incoming_d)
            if key in seen_local:
                break
            seen_local.add(key)

            used_dirs: Set[int] = set()
            for u in g.adj.get(cur_v, set()):
                e = g._norm_edge(cur_v, u)
                if e in deleted:
                    continue
                d = _edge_dir_from(g, cur_v, u)
                if d is not None:
                    used_dirs.add(d)
            if not used_dirs:
                break

            admissible = admissible_dirs_for_vertex(g, cur_v, enforce_symmetry=False)
            cand_dirs = _symmetric_candidate_dirs(sorted(used_dirs), admissible, incoming_d=incoming_d)
            if not cand_dirs:
                break

            best_choice: Optional[Tuple[int, float, int, int, int, int, int]] = None
            for d in cand_dirs:
                hit = _pick_incident_edge_in_dir(g, cur_v, d, deleted)
                if hit is None:
                    continue
                ei, ej, next_v = hit
                remain = set(used_dirs)
                remain.discard(d)
                ke = _kawasaki_residual_from_dirs(sorted(remain))
                sat = 0 if ke <= 1e-8 else 1
                score = (sat, ke, _dir_gap_steps(d, incoming_d), min(ei, ej), max(ei, ej), d, next_v)
                if best_choice is None or score < best_choice:
                    best_choice = score
            if best_choice is None:
                break
            _, _, _, ei, ej, d_out, next_v = best_choice
            e = (ei, ej)
            if e in deleted:
                break
            deleted.add(e)
            cur_v = next_v
            incoming_d = (d_out + ANGLE_COUNT // 2) % ANGLE_COUNT
    return deleted


def _expand_delete_edges_with_symmetry(
    g: GridCreaseGraph,
    edges: Set[Tuple[int, int]],
) -> Optional[Set[Tuple[int, int]]]:
    out: Set[Tuple[int, int]] = set(edges)
    for i, j in list(edges):
        mi = g.mirror_vertex_idx(i)
        mj = g.mirror_vertex_idx(j)
        if mi is None or mj is None:
            return None
        em = g._norm_edge(mi, mj)
        if em not in g.edges:
            return None
        out.add(em)
    return out


def _deactivate_isolated_noncorner_vertices(g: GridCreaseGraph, corner_ids: Sequence[int]) -> None:
    cset = set(corner_ids)
    for v in list(g.active_vertices):
        if v in cset:
            continue
        if g.adj.get(v) and len(g.adj[v]) > 0:
            continue
        g._clear_ray_hit_row(v)
        g.active_vertices.discard(v)
        g.adj.pop(v, None)
        g.ray_next.pop(v, None)
        g.ray_hit.pop(v, None)
        g.ray_dirty.discard(v)
        g.incident_dirs_cache.pop(v, None)
        g.incident_dirs_dirty.discard(v)
        g.kawasaki_cache.pop(v, None)
        g.kawasaki_dirty.discard(v)


def _refresh_graph_by_pruning(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int,
    kawasaki_tol: float,
    enforce_symmetry: bool = True,
    max_candidates: int = 24,
) -> Tuple[GridCreaseGraph, int]:
    h = clone_graph(g)
    best_sc = global_score(
        h,
        corner_ids=corner_ids,
        max_deg=max_deg,
        min_corner_lines=min_corner_lines,
        kawasaki_tol=kawasaki_tol,
    )
    best_ck = priority_corner_kawasaki_score(h, corner_ids=corner_ids, tol=kawasaki_tol)

    def edge_center_dist2(e: Tuple[int, int]) -> float:
        i, j = e
        x1, y1 = h.points_f[i]
        x2, y2 = h.points_f[j]
        cx = 0.5 * (x1 + x2)
        cy = 0.5 * (y1 + y2)
        return (cx - 0.5) ** 2 + (cy - 0.5) ** 2

    candidates = [e for e in h.edges if e not in h.boundary_edges]
    candidates.sort(
        key=lambda e: (
            edge_center_dist2(e),
            -h.edge_birth.get(e, -1),
        )
    )

    removed_total = 0
    tried_groups: Set[Tuple[Tuple[int, int], ...]] = set()
    for e in candidates[:max_candidates]:
        if e not in h.edges or e in h.boundary_edges:
            continue
        del_edges: Set[Tuple[int, int]] = {e}
        if enforce_symmetry:
            ex = _expand_delete_edges_with_symmetry(h, del_edges)
            if ex is None:
                continue
            del_edges = ex
        if any(de in h.boundary_edges for de in del_edges):
            continue

        group_key = tuple(sorted(del_edges))
        if group_key in tried_groups:
            continue
        tried_groups.add(group_key)

        trial = clone_graph(h)
        for di, dj in sorted(del_edges):
            trial.remove_edge(di, dj)
        _deactivate_isolated_noncorner_vertices(trial, corner_ids=corner_ids)
        if enforce_symmetry and not diagonal_symmetry_ok(trial):
            continue

        sc = global_score(
            trial,
            corner_ids=corner_ids,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        ck = priority_corner_kawasaki_score(trial, corner_ids=corner_ids, tol=kawasaki_tol)
        if sc <= best_sc and ck <= best_ck:
            h = trial
            best_sc = sc
            best_ck = ck
            removed_total += len(del_edges)

    return h, removed_total


def apply_open_sink_with_delete_fallback(
    g: GridCreaseGraph,
    v_idx: int,
    dir_idx: int,
    corner_ids: Sequence[int],
    enforce_symmetry: bool = True,
    max_bounces: int = 14,
    enable_repair: bool = True,
    kawasaki_tol: float = 1e-8,
    delete_chain_steps: int = 6,
    stats: Optional[Dict[str, int]] = None,
    skip_direct: bool = False,
    count_attempt: bool = True,
) -> Optional[GridCreaseGraph]:
    if stats is not None and count_attempt:
        stats["open_sink_attempt"] = stats.get("open_sink_attempt", 0) + 1
    if not skip_direct:
        out = apply_open_sink_action(
            g,
            v_idx=v_idx,
            dir_idx=dir_idx,
            enforce_symmetry=enforce_symmetry,
            max_bounces=max_bounces,
            enable_repair=enable_repair,
            stats=stats,
        )
        if out is not None:
            if stats is not None:
                stats["open_sink_success_direct"] = stats.get("open_sink_success_direct", 0) + 1
            return out
    if stats is not None:
        stats["open_sink_fallback_enter"] = stats.get("open_sink_fallback_enter", 0) + 1

    hit = g.first_hit_edge(v_idx, dir_idx)
    if hit is None:
        if stats is not None:
            stats["open_sink_fallback_no_first_hit"] = stats.get("open_sink_fallback_no_first_hit", 0) + 1
        return None
    i, j, hit_pos, _ = hit
    # Requested behavior: no delete fallback when first hit is an existing vertex.
    if hit_pos != 0:
        if stats is not None:
            stats["open_sink_fallback_first_hit_vertex"] = stats.get("open_sink_fallback_first_hit_vertex", 0) + 1
        return None
    blocker = g._norm_edge(i, j)
    if blocker in g.boundary_edges:
        if stats is not None:
            stats["open_sink_fallback_blocker_boundary"] = stats.get("open_sink_fallback_blocker_boundary", 0) + 1
        return None

    del_edges = _collect_delete_chain_from_blocker(g, blocker, max_steps=delete_chain_steps)
    if enforce_symmetry:
        ex = _expand_delete_edges_with_symmetry(g, del_edges)
        if ex is None:
            if stats is not None:
                stats["open_sink_fallback_symmetry_missing"] = stats.get("open_sink_fallback_symmetry_missing", 0) + 1
            return None
        del_edges = ex
    if len(del_edges) < 2:
        if stats is not None:
            stats["open_sink_fallback_too_few_delete_edges"] = stats.get("open_sink_fallback_too_few_delete_edges", 0) + 1
        return None
    for e in del_edges:
        if e in g.boundary_edges:
            if stats is not None:
                stats["open_sink_fallback_delete_hits_boundary"] = stats.get("open_sink_fallback_delete_hits_boundary", 0) + 1
            return None

    h_del = clone_graph(g)
    for ei, ej in sorted(del_edges):
        h_del.remove_edge(ei, ej)

    out2 = apply_open_sink_action(
        h_del,
        v_idx=v_idx,
        dir_idx=dir_idx,
        enforce_symmetry=enforce_symmetry,
        max_bounces=max_bounces,
        enable_repair=enable_repair,
        stats=stats,
    )
    if out2 is None:
        if stats is not None:
            stats["open_sink_fallback_retry_failed"] = stats.get("open_sink_fallback_retry_failed", 0) + 1
        return None
    if priority_corner_kawasaki_score(out2, corner_ids=corner_ids, tol=kawasaki_tol) > priority_corner_kawasaki_score(
        g, corner_ids=corner_ids, tol=kawasaki_tol
    ):
        if stats is not None:
            stats["open_sink_fallback_kawasaki_worse"] = stats.get("open_sink_fallback_kawasaki_worse", 0) + 1
        return None
    _deactivate_isolated_noncorner_vertices(out2, corner_ids=corner_ids)
    if stats is not None:
        stats["open_sink_fallback_success"] = stats.get("open_sink_fallback_success", 0) + 1
    return out2


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
        # For seeding, prefer finishing by a direct segment when no interior crossing exists.
        # This avoids open-sink style overshoot when the goal corner is currently isolated.
        if not _crosses_existing_edges(g, cur, goal_v):
            g.add_edge(cur, goal_v, boundary=False)
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
                    mc = h.mirror_vertex_idx(c)
                    if mc is None:
                        continue
                    for sv in trip:
                        msv = h.mirror_vertex_idx(sv)
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


def seed_direct_corner_connections(
    g: GridCreaseGraph,
    corner_ids: Sequence[int],
    enforce_symmetry: bool = True,
) -> None:
    ids = list(corner_ids)
    min_corner_lines_seed = 2
    kawasaki_tol_seed = 1e-8
    boundary_corner_weight = 0.35

    def _corner_deficit_total(h: GridCreaseGraph) -> float:
        total = 0.0
        for cv in corner_ids:
            deficit = max(0, min_corner_lines_seed - corner_line_count(h, cv))
            if deficit <= 0:
                continue
            if _is_boundary_vertex(h, cv):
                total += boundary_corner_weight * float(deficit)
            else:
                total += float(deficit)
        return total

    pairs: List[Tuple[float, int, int]] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            u = ids[i]
            v = ids[j]
            p = g.points[u]
            q = g.points[v]
            if not _is_aligned_with_16_dirs(p, q):
                continue
            ux, uy = g.points_f[u]
            vx, vy = g.points_f[v]
            dist2 = (ux - vx) ** 2 + (uy - vy) ** 2
            pairs.append((dist2, u, v))

    # Add shorter corner-corner segments first, allowing split-at-intersections transactions.
    pairs.sort(key=lambda t: t[0])
    attempted_sym_keys: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
    for _, u, v in pairs:
        if _is_square_corner_vertex(g, u) or _is_square_corner_vertex(g, v):
            continue
        e = (u, v) if u < v else (v, u)
        if e in g.edges:
            continue

        mirror_edge = e
        if enforce_symmetry:
            mu = g.mirror_vertex_idx(u)
            mv = g.mirror_vertex_idx(v)
            if mu is None or mv is None:
                continue
            mirror_edge = (mu, mv) if mu < mv else (mv, mu)
            key = (e, mirror_edge) if e <= mirror_edge else (mirror_edge, e)
            if key in attempted_sym_keys:
                continue
            attempted_sym_keys.add(key)

        before_ck = priority_corner_kawasaki_score(g, corner_ids=corner_ids, tol=kawasaki_tol_seed)
        before_k_bad = kawasaki_score(g, tol=kawasaki_tol_seed)[0]
        before_def = _corner_deficit_total(g)

        need_vertices: Set[int] = {u, v}
        if enforce_symmetry:
            need_vertices.update(mirror_edge)

        endpoint_needed = False
        for vv in need_vertices:
            vv_lines = corner_line_count(g, vv)
            vv_need = (vv_lines < min_corner_lines_seed) if (not _is_boundary_vertex(g, vv)) else (vv_lines < 1)
            endpoint_needed = endpoint_needed or vv_need

        trial = clone_graph(g)
        ok = _add_segment_with_splits_ids(trial, u, v, max_steps=64)
        if ok and enforce_symmetry and mirror_edge != e:
            ok = _add_segment_with_splits_ids(trial, mirror_edge[0], mirror_edge[1], max_steps=64)
        if ok:
            if enforce_symmetry and not diagonal_symmetry_ok(trial):
                continue
            after_ck = priority_corner_kawasaki_score(trial, corner_ids=corner_ids, tol=kawasaki_tol_seed)
            after_k_bad = kawasaki_score(trial, tol=kawasaki_tol_seed)[0]
            after_def = _corner_deficit_total(trial)

            ck_improved = after_ck < before_ck
            deficit_improved = after_def < before_def

            # Exclude seeds that make interior Kawasaki much worse without line-deficit benefit.
            if after_k_bad > before_k_bad + 1 and not deficit_improved:
                continue
            # If neither priority-corner Kawasaki nor line deficit improves, skip dense additions.
            if (not ck_improved) and (not deficit_improved) and (not endpoint_needed):
                continue
            # Do not accept clear degradation on priority-corner Kawasaki unless deficit improves.
            if after_ck > before_ck and not deficit_improved:
                continue

            adopt_graph_state(g, trial)


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
            1 if _is_boundary_vertex(g, v) else 0,
            -vertex_kawasaki_error(g, v),
            -corner_condition_error(g, v, max_deg=max_deg),
            -(max(0, min_corner_lines - corner_line_count(g, v))),
        ),
    )


def graph_state_key(g: GridCreaseGraph) -> Tuple:
    return (g.state_hash1, g.state_hash2, len(g.edges))


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
    enable_open_sink_repair: bool = True,
    open_sink_max_bounces: int = 14,
    min_corner_lines: int = 2,
    kawasaki_tol: float = 1e-8,
    enable_corner_kawasaki_repair: bool = True,
    enable_triangle_macro: bool = False,
    require_corner_kawasaki: bool = True,
    search_stats: Optional[Dict[str, int]] = None,
    refresh_every_nodes: int = 30,
    refresh_max_candidates: int = 24,
    dir_top_k: int = 4,
    priority_top_n: int = 6,
    stop_on_corner_clear: bool = False,
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
        if stop_on_corner_clear and sc[1] == 0:
            solved = True
            _inc("stopped_corner_clear")
            best = clone_graph(state)
            best_score = sc
            return
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

        if refresh_every_nodes > 0 and depth > 0 and (node_counter % refresh_every_nodes == 0):
            _inc("refresh_trigger")
            refreshed, removed = _refresh_graph_by_pruning(
                state,
                corner_ids=corner_ids,
                max_deg=max_deg,
                min_corner_lines=min_corner_lines,
                kawasaki_tol=kawasaki_tol,
                enforce_symmetry=enforce_symmetry,
                max_candidates=refresh_max_candidates,
            )
            if removed > 0:
                rkey = graph_state_key(refreshed)
                if rkey in seen:
                    _inc("refresh_reject_seen")
                else:
                    rsc = global_score(
                        refreshed,
                        corner_ids=corner_ids,
                        max_deg=max_deg,
                        min_corner_lines=min_corner_lines,
                        kawasaki_tol=kawasaki_tol,
                    )
                    rck = priority_corner_kawasaki_score(refreshed, corner_ids=corner_ids, tol=kawasaki_tol)
                    if rsc <= sc and (not require_corner_kawasaki or rck[0] <= ck[0]):
                        seen.add(rkey)
                        state = refreshed
                        sc = rsc
                        ck = rck
                        _inc("refresh_applied")
                        _inc("refresh_removed_edges", removed)
                        if sc < best_score:
                            best = clone_graph(state)
                            best_score = sc
                    else:
                        _inc("refresh_reject_worse")
            else:
                _inc("refresh_nochange")

        priority = violating_vertex_priority(
            state,
            corner_ids=corner_ids,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
            kawasaki_tol=kawasaki_tol,
        )
        child_pool: List[Tuple[Tuple[int, int, int, float, float, float], GridCreaseGraph]] = []
        seen_move_equiv: Set[Tuple] = set()
        for v in priority[: max(1, priority_top_n)]:
            used = used_dir_indices(state, v, include_boundary=False)
            feasible_dirs: List[int] = []
            first_hit_map: Dict[int, Optional[int]] = {}
            row_v = state.ensure_ray_next(v)
            for d in admissible_dirs_for_vertex(state, v, enforce_symmetry=enforce_symmetry):
                _inc("candidate_dirs_total")
                if d in used:
                    _inc("reject_used_dir")
                    continue
                hit_v = row_v[d]
                if hit_v is None:
                    _inc("reject_no_ray_hit")
                    continue
                feasible_dirs.append(d)
                first_hit_map[d] = hit_v
            if not feasible_dirs:
                continue
            trial_dirs = _topk_dirs_for_vertex(
                state,
                v_idx=v,
                dirs=feasible_dirs,
                used_dirs=used,
                k=dir_top_k,
                first_hit_map=first_hit_map,
            )
            if len(trial_dirs) < len(feasible_dirs):
                _inc("reject_topk_drop", len(feasible_dirs) - len(trial_dirs))
            mirror_v: Optional[int] = None
            mirror_row: Optional[List[Optional[int]]] = None
            if enforce_symmetry:
                mirror_v = state.mirror_vertex_idx(v)
                if mirror_v is not None:
                    mirror_row = state.ensure_ray_next(mirror_v)
            for d in trial_dirs:
                first_hit = first_hit_map.get(d)
                if first_hit is None:
                    _inc("reject_no_first_hit")
                    continue
                first_key: Tuple = ("V", first_hit)
                mirror_key: Optional[Tuple] = None
                if enforce_symmetry:
                    if mirror_v is None:
                        mirror_key = ("MISSING_MIRROR_VERTEX",)
                    else:
                        md = mirrored_dir_idx(d)
                        mhit = mirror_row[md] if mirror_row is not None else None
                        mirror_key = None if mhit is None else ("V", mhit)
                mk = (v, first_key, mirror_key)
                if mk in seen_move_equiv:
                    _inc("reject_equiv_move")
                    continue
                seen_move_equiv.add(mk)
                if enable_open_sink:
                    h = apply_open_sink_with_delete_fallback(
                        state,
                        v_idx=v,
                        dir_idx=d,
                        corner_ids=corner_ids,
                        enforce_symmetry=enforce_symmetry,
                        max_bounces=open_sink_max_bounces,
                        enable_repair=enable_open_sink_repair,
                        kawasaki_tol=kawasaki_tol,
                        stats=stats,
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
                    h = apply_ray_action(state, v_idx=v, dir_idx=d, enforce_symmetry=enforce_symmetry, stats=stats)
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
    enforce_symmetry: bool = True,
    use_local_ray_dirty: bool = False,
) -> Tuple[GridCreaseGraph, List[int]]:
    points, p2i = enumerate_grid_points(a_max=a_max, b_max=b_max, k_max=k_max)
    g = GridCreaseGraph(points=points, p2i=p2i, use_local_ray_dirty=use_local_ray_dirty)
    g.init_square_boundary()
    corner_ids = [g.add_vertex(p) for p in corners]
    # Seed direct corner-to-corner connections on the 16-direction grid.
    seed_direct_corner_connections(g, corner_ids, enforce_symmetry=enforce_symmetry)
    # Seed the main diagonal y=x.
    # Using split-aware insertion keeps diagonal connectivity even when intersections exist.
    v00 = g.add_vertex(PointE(ZERO, ZERO))
    v11 = g.add_vertex(PointE(ONE, ONE))
    _add_segment_with_splits_ids(g, v00, v11, max_steps=128)
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
            max_k = max(max_k, z.k)
            max_abs_a = max(max_abs_a, abs(z.a))
            max_abs_b = max(max_abs_b, abs(z.b))
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


def _parse_dyadic_coeff(tok: str) -> Tuple[int, int]:
    t = tok.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("empty dyadic coefficient")
    sign = 1
    if t.startswith("-"):
        sign = -1
        t = t[1:]
    elif t.startswith("+"):
        t = t[1:]
    if not t:
        raise ValueError("invalid dyadic coefficient")
    if "." in t:
        ip, fp = t.split(".", 1)
        if not ip:
            ip = "0"
        if not fp or (not ip.isdigit()) or (not fp.isdigit()):
            raise ValueError(f"invalid decimal coefficient: {tok}")
        den = 10 ** len(fp)
        num = int(ip) * den + int(fp)
    elif "/" in t:
        xs = t.split("/")
        if len(xs) != 2 or (not xs[0]) or (not xs[1]):
            raise ValueError(f"invalid rational coefficient: {tok}")
        num = int(xs[0])
        den = int(xs[1])
        if den == 0:
            raise ValueError("division by zero in coefficient")
        if den < 0:
            den = -den
            num = -num
    else:
        if not t.isdigit():
            raise ValueError(f"invalid integer coefficient: {tok}")
        return _q2_reduce(sign * int(t), 0, 0)[0], 0

    num *= sign
    if den < 0:
        den = -den
        num = -num
    g = gcd(abs(num), den)
    num //= g
    den //= g
    if not _is_power_of_two(den):
        raise ValueError(f"non-dyadic coefficient is not supported: {tok}")
    k = den.bit_length() - 1
    a, _, k = _q2_reduce(num, 0, k)
    return (a, k)


def _parse_qsqrt2_token(tok: str) -> Qsqrt2:
    t = tok.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("empty token")
    if t in ("sqrt2", "sqrt(2)"):
        return Qsqrt2(0, 1, 0)
    if t in ("1/sqrt2", "1/sqrt(2)", "sqrt2/2", "sqrt(2)/2"):
        return INV_SQRT2
    if "sqrt2" in t or "sqrt(2)" in t:
        t = t.replace("sqrt(2)", "sqrt2")
        sign = 1
        if t.startswith("-"):
            sign = -1
            t = t[1:]
        if t == "sqrt2":
            return Qsqrt2(0, sign, 0)
        if t.endswith("*sqrt2"):
            num, k = _parse_dyadic_coeff(t[:-6])
            return Qsqrt2(0, sign * num, k)
        if t.startswith("sqrt2/"):
            num, k = _parse_dyadic_coeff("1/" + t.split("/")[1])
            return Qsqrt2(0, sign * num, k)
        raise ValueError(f"unsupported sqrt2 token: {tok}")
    num, k = _parse_dyadic_coeff(t)
    return Qsqrt2(num, 0, k)


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


def _merge_search_stats(dst: Dict[str, int], src: Dict[str, int]) -> None:
    for k, v in src.items():
        if k.startswith("expand_need_"):
            dst[k] = max(dst.get(k, 0), v)
        else:
            dst[k] = dst.get(k, 0) + v


def _expand_request_from_stats(stats: Dict[str, int]) -> Optional[Tuple[int, int, int]]:
    ra = stats.get("expand_need_a_max", 0)
    rb = stats.get("expand_need_b_max", 0)
    rk = stats.get("expand_need_k_max", 0)
    if ra <= 0 and rb <= 0 and rk <= 0:
        return None
    return (ra, rb, rk)


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
    enable_open_sink_repair: bool = True,
    open_sink_max_bounces: int = 14,
    min_corner_lines: int = 2,
    kawasaki_tol: float = 1e-8,
    enable_corner_kawasaki_repair: bool = True,
    enable_triangle_macro: bool = False,
    require_corner_kawasaki: bool = True,
    staged_k_relax: bool = False,
    k_start: int = 1,
    dir_top_k: int = 4,
    priority_top_n: int = 6,
    use_local_ray_dirty: bool = False,
    stop_on_corner_clear: bool = False,
    auto_expand_grid: bool = False,
    auto_expand_max_rounds: int = 3,
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

    a_work = a_max
    b_work = b_max

    g, corner_ids = make_grid_graph(
        corners,
        a_max=a_work,
        b_max=b_work,
        k_max=ks,
        enforce_symmetry=enforce_symmetry,
        use_local_ray_dirty=use_local_ray_dirty,
    )
    before_stats = graph_stats(g)
    before = corner_score(g, corner_ids=corner_ids, max_deg=corner_max_deg, min_corner_lines=min_corner_lines)
    before_k = kawasaki_score(g, tol=kawasaki_tol)
    before_ck = priority_corner_kawasaki_score(g, corner_ids=corner_ids, tol=kawasaki_tol)

    def _search_stage(
        g_stage: GridCreaseGraph,
        corner_stage: List[int],
        stage_k: int,
    ) -> Tuple[GridCreaseGraph, List[int], int]:
        nonlocal a_work, b_work
        g_local = g_stage
        c_local = list(corner_stage)
        k_local = stage_k
        rounds = 0
        while True:
            round_stats: Dict[str, int] = {}
            best_local = dfs_repair_corners(
                g_local,
                corner_ids=c_local,
                max_deg=corner_max_deg,
                max_depth=max_depth,
                branch_per_node=branch_per_node,
                allow_violations=allow_violations,
                max_nodes=max_nodes,
                enforce_symmetry=enforce_symmetry,
                enable_open_sink=enable_open_sink,
                enable_open_sink_repair=enable_open_sink_repair,
                open_sink_max_bounces=open_sink_max_bounces,
                min_corner_lines=min_corner_lines,
                kawasaki_tol=kawasaki_tol,
                enable_corner_kawasaki_repair=enable_corner_kawasaki_repair,
                enable_triangle_macro=enable_triangle_macro,
                require_corner_kawasaki=require_corner_kawasaki,
                search_stats=round_stats,
                dir_top_k=dir_top_k,
                priority_top_n=priority_top_n,
                stop_on_corner_clear=stop_on_corner_clear,
            )
            _merge_search_stats(search_stats, round_stats)
            if not auto_expand_grid:
                return best_local, c_local, k_local

            req = _expand_request_from_stats(round_stats)
            if req is None:
                return best_local, c_local, k_local
            need_a, need_b, need_k = req
            target_a = a_work
            target_b = b_work
            target_k = k_local if staged_k_relax else max(k_local, need_k)
            # Prefer k expansion first. If k is still insufficient, expand only k in this round.
            # Expand a/b only after k is satisfied (or when staged_k_relax fixes k per stage).
            if staged_k_relax or target_k <= k_local:
                target_a = max(a_work, need_a)
                target_b = max(b_work, need_b)
            if target_a <= a_work and target_b <= b_work and target_k <= k_local:
                return best_local, c_local, k_local
            if rounds >= max(0, auto_expand_max_rounds):
                search_stats["auto_expand_round_limit"] = search_stats.get("auto_expand_round_limit", 0) + 1
                return best_local, c_local, k_local

            rounds += 1
            search_stats["auto_expand_trigger"] = search_stats.get("auto_expand_trigger", 0) + 1
            if target_k > k_local and target_a == a_work and target_b == b_work:
                search_stats["auto_expand_k_only"] = search_stats.get("auto_expand_k_only", 0) + 1
                expand_mode = "k_only"
            else:
                search_stats["auto_expand_with_ab"] = search_stats.get("auto_expand_with_ab", 0) + 1
                expand_mode = "with_ab"
            a_work = target_a
            b_work = target_b
            ng, ncorner_ids = make_grid_graph(
                corners,
                a_max=a_work,
                b_max=b_work,
                k_max=target_k,
                enforce_symmetry=enforce_symmetry,
                use_local_ray_dirty=use_local_ray_dirty,
            )
            remap_graph_to_new_grid(best_local, ng)
            g_local = ng
            c_local = ncorner_ids
            k_local = target_k
            stage_logs.append(
                {
                    "type": "auto_expand",
                    "mode": expand_mode,
                    "a_max": a_work,
                    "b_max": b_work,
                    "k_max": k_local,
                    "stats": graph_stats(g_local),
                }
            )

    best = clone_graph(g)
    effective_k = ks
    if staged_k_relax:
        for kcur in range(ks, k_max + 1):
            if kcur > ks:
                ng, ncorner_ids = make_grid_graph(
                    corners,
                    a_max=a_work,
                    b_max=b_work,
                    k_max=kcur,
                    enforce_symmetry=enforce_symmetry,
                    use_local_ray_dirty=use_local_ray_dirty,
                )
                remap_graph_to_new_grid(best, ng)
                g = ng
                corner_ids = ncorner_ids
            best, corner_ids, effective_k = _search_stage(g, corner_ids, kcur)
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
        best, corner_ids, effective_k = _search_stage(g, corner_ids, ks)

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
            "enable_open_sink_repair": enable_open_sink_repair,
            "open_sink_max_bounces": open_sink_max_bounces,
            "min_corner_lines": min_corner_lines,
            "kawasaki_tol": kawasaki_tol,
            "enable_corner_kawasaki_repair": enable_corner_kawasaki_repair,
            "enable_triangle_macro": enable_triangle_macro,
            "require_corner_kawasaki": require_corner_kawasaki,
            "staged_k_relax": staged_k_relax,
            "k_start": k_start,
            "dir_top_k": dir_top_k,
            "priority_top_n": priority_top_n,
            "use_local_ray_dirty": use_local_ray_dirty,
            "stop_on_corner_clear": stop_on_corner_clear,
            "auto_expand_grid": auto_expand_grid,
            "auto_expand_max_rounds": auto_expand_max_rounds,
            "show_order": show_order,
            "a_max_effective": a_work,
            "b_max_effective": b_work,
            "k_max_effective": effective_k,
        },
        "stats_before": before_stats,
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
        "stage_logs": stage_logs if staged_k_relax or auto_expand_grid else None,
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
    parser.add_argument("--dir-top-k", type=int, default=4)
    parser.add_argument("--priority-top-n", type=int, default=6)
    parser.add_argument(
        "--local-ray-dirty",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument("--stop-on-corner-clear", action="store_true")
    parser.add_argument("--show-order", action="store_true")
    parser.add_argument("--auto-expand-grid", action="store_true")
    parser.add_argument("--auto-expand-max-rounds", type=int, default=3)
    parser.add_argument("--no-symmetry", action="store_true")
    parser.add_argument("--no-open-sink", action="store_true")
    parser.add_argument("--no-open-sink-repair", action="store_true")
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
        show_order=args.show_order,
        render_image=not args.no_render,
        out_path=args.out_path,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
