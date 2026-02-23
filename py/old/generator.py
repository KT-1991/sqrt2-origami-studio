from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from math import atan2, cos, pi, sin
from typing import Dict, List, Optional, Sequence, Set, Tuple


# --------------------
# Exact number scaffold
# --------------------


@dataclass(frozen=True)
class Qsqrt2:
    """a + b*sqrt(2), with rational a,b."""

    a: Fraction
    b: Fraction

    @staticmethod
    def from_int(n: int) -> "Qsqrt2":
        return Qsqrt2(Fraction(n), Fraction(0))

    def __add__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(self.a + o.a, self.b + o.b)

    def __sub__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(self.a - o.a, self.b - o.b)

    def __mul__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(self.a * o.a + 2 * self.b * o.b, self.a * o.b + self.b * o.a)

    def inv(self) -> "Qsqrt2":
        den = self.a * self.a - 2 * self.b * self.b
        return Qsqrt2(self.a / den, -self.b / den)

    def __truediv__(self, o: "Qsqrt2") -> "Qsqrt2":
        return self * o.inv()

    def approx(self) -> float:
        return float(self.a) + float(self.b) * (2**0.5)


# --------------------
# Discrete geometry setup
# --------------------

EPS = 1e-9
CORNER_STRICT_EPS = 1e-8
CORNER_MAX_DEG = 90.0
ANGLE_COUNT = 16
DIRS: List[Tuple[float, float]] = [
    (cos(i * 2 * pi / ANGLE_COUNT), sin(i * 2 * pi / ANGLE_COUNT)) for i in range(ANGLE_COUNT)
]


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def set_corner_max_deg(deg: float) -> None:
    """
    Set strict corner threshold in degrees.
    Corner condition uses: every sector < deg.
    """
    global CORNER_MAX_DEG
    if not (0.0 < deg < 180.0):
        raise ValueError(f"corner_max_deg must be in (0, 180), got {deg}")
    CORNER_MAX_DEG = float(deg)


def corner_threshold_rad() -> float:
    return CORNER_MAX_DEG * pi / 180.0 - CORNER_STRICT_EPS


def in_square(p: Tuple[float, float], eps: float = 1e-9) -> bool:
    x, y = p
    return -eps <= x <= 1.0 + eps and -eps <= y <= 1.0 + eps


def pt_key(p: Tuple[float, float], tol: float = 1e-9) -> Tuple[int, int]:
    return (round(p[0] / tol), round(p[1] / tol))


def cross(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


@dataclass
class Line:
    # n.x * x + n.y * y = c
    nx: float
    ny: float
    c: float


def make_line_through_point_dir(p: Tuple[float, float], dir_idx: int) -> Line:
    dx, dy = DIRS[dir_idx]
    nx, ny = -dy, dx
    c = nx * p[0] + ny * p[1]
    return Line(nx, ny, c)


def line_intersection(l1: Line, l2: Line) -> Optional[Tuple[float, float]]:
    det = l1.nx * l2.ny - l1.ny * l2.nx
    if abs(det) < EPS:
        return None
    x = (l1.c * l2.ny - l2.c * l1.ny) / det
    y = (l1.nx * l2.c - l2.nx * l1.c) / det
    return (x, y)


def line_key(line: Line, dir_idx: int, tol: float = 1e-9) -> Tuple[int, int]:
    # Opposite directions define the same undirected line.
    base = dir_idx % 8
    return (base, round(line.c / tol))


# --------------------
# Stage 1: candidate vertex enumeration
# --------------------


def enumerate_candidate_vertices(
    initial_vertices: Sequence[Tuple[float, float]],
    depth: int = 2,
    max_lines_per_iter: int = 2000,
) -> List[Tuple[float, float]]:
    """
    Enumerate reachable vertex candidates by iteratively adding 16-direction lines
    through known points and intersecting them.
    """
    points: Dict[Tuple[int, int], Tuple[float, float]] = {}
    frontier: List[Tuple[float, float]] = []
    for p in initial_vertices:
        k = pt_key(p)
        if k not in points:
            points[k] = p
            frontier.append(p)

    # Square corners help stabilize early intersections.
    for p in [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]:
        k = pt_key(p)
        if k not in points:
            points[k] = p
            frontier.append(p)

    known_lines: Dict[Tuple[int, int], Line] = {}

    for _ in range(depth):
        new_line_keys: List[Tuple[int, int]] = []
        for p in frontier:
            for d in range(ANGLE_COUNT):
                ln = make_line_through_point_dir(p, d)
                k = line_key(ln, d)
                if k not in known_lines:
                    known_lines[k] = ln
                    new_line_keys.append(k)
                if len(new_line_keys) >= max_lines_per_iter:
                    break
            if len(new_line_keys) >= max_lines_per_iter:
                break

        next_frontier: List[Tuple[float, float]] = []
        all_keys = list(known_lines.keys())
        for k1, k2 in combinations(all_keys, 2):
            p = line_intersection(known_lines[k1], known_lines[k2])
            if p is None or not in_square(p):
                continue
            p = (clamp01(p[0]), clamp01(p[1]))
            pk = pt_key(p)
            if pk not in points:
                points[pk] = p
                next_frontier.append(p)

        if not next_frontier:
            break
        frontier = next_frontier

    return list(points.values())


# --------------------
# Stage 2: ray shooting and segment split graph
# --------------------


class CreaseGraph:
    def __init__(self, eps: float = 1e-9):
        self.eps = eps
        self.vertices: List[Tuple[float, float]] = []
        self.edges: Set[Tuple[int, int]] = set()
        self.boundary_edges: Set[Tuple[int, int]] = set()

    def add_vertex(self, p: Tuple[float, float]) -> int:
        k = pt_key(p, self.eps)
        for i, q in enumerate(self.vertices):
            if pt_key(q, self.eps) == k:
                return i
        self.vertices.append((float(p[0]), float(p[1])))
        return len(self.vertices) - 1

    def add_edge(self, i: int, j: int, boundary: bool = False) -> None:
        if i == j:
            return
        e = (i, j) if i < j else (j, i)
        self.edges.add(e)
        if boundary:
            self.boundary_edges.add(e)
        elif e in self.boundary_edges:
            self.boundary_edges.discard(e)

    def has_edge(self, i: int, j: int) -> bool:
        e = (i, j) if i < j else (j, i)
        return e in self.edges

    def init_square_boundary(self) -> None:
        v0 = self.add_vertex((0.0, 0.0))
        v1 = self.add_vertex((1.0, 0.0))
        v2 = self.add_vertex((1.0, 1.0))
        v3 = self.add_vertex((0.0, 1.0))
        self.add_edge(v0, v1, boundary=True)
        self.add_edge(v1, v2, boundary=True)
        self.add_edge(v2, v3, boundary=True)
        self.add_edge(v3, v0, boundary=True)

    def _ray_segment_hit(
        self,
        origin: Tuple[float, float],
        d: Tuple[float, float],
        a: Tuple[float, float],
        b: Tuple[float, float],
    ) -> Optional[Tuple[float, float, Tuple[float, float]]]:
        vx, vy = b[0] - a[0], b[1] - a[1]
        ox, oy = origin
        dx, dy = d
        ax, ay = a

        denom = cross(dx, dy, vx, vy)
        if abs(denom) < self.eps:
            return None

        wx, wy = ax - ox, ay - oy
        t = cross(wx, wy, vx, vy) / denom
        u = cross(wx, wy, dx, dy) / denom

        if t <= self.eps:
            return None
        if u < -self.eps or u > 1.0 + self.eps:
            return None

        px = ox + t * dx
        py = oy + t * dy
        return (t, u, (px, py))

    def shoot_ray_and_split(self, origin_idx: int, dir_idx: int) -> Optional[Tuple[int, int]]:
        origin = self.vertices[origin_idx]
        d = DIRS[dir_idx]

        best = None
        best_edge = None
        for i, j in list(self.edges):
            a, b = self.vertices[i], self.vertices[j]
            hit = self._ray_segment_hit(origin, d, a, b)
            if hit is None:
                continue
            t, u, p = hit
            if best is None or t < best[0]:
                best = (t, u, p)
                best_edge = (i, j)

        if best is None or best_edge is None:
            return None

        _, u, p = best
        i, j = best_edge

        # If hit is at existing endpoint, connect directly.
        if u <= self.eps:
            hit_idx = i
        elif u >= 1.0 - self.eps:
            hit_idx = j
        else:
            hit_idx = self.add_vertex(p)
            old_e = (i, j) if i < j else (j, i)
            was_boundary = old_e in self.boundary_edges
            self.edges.discard(old_e)
            self.boundary_edges.discard(old_e)
            self.add_edge(i, hit_idx, boundary=was_boundary)
            self.add_edge(hit_idx, j, boundary=was_boundary)

        if not self.has_edge(origin_idx, hit_idx):
            self.add_edge(origin_idx, hit_idx, boundary=False)
        return (origin_idx, hit_idx)


def incident_angles(g: CreaseGraph, v_idx: int, include_boundary: bool = False) -> List[float]:
    vx, vy = g.vertices[v_idx]
    angs: List[float] = []
    for i, j in g.edges:
        e = (i, j) if i < j else (j, i)
        if not include_boundary and e in g.boundary_edges:
            continue
        if i != v_idx and j != v_idx:
            continue
        u = j if i == v_idx else i
        ux, uy = g.vertices[u]
        ang = atan2(uy - vy, ux - vx)
        if ang < 0:
            ang += 2 * pi
        angs.append(ang)
    return sorted(angs)


def unique_angles(angles: Sequence[float], tol: float = 1e-8) -> List[float]:
    """
    Merge nearly identical directions. This avoids fake 0/360 sectors caused by
    duplicated collinear edges from the same vertex.
    """
    if not angles:
        return []
    arr = sorted(angles)
    out: List[float] = [arr[0]]
    for a in arr[1:]:
        if abs(a - out[-1]) > tol:
            out.append(a)
    # Merge wrap-around near 0 and 2pi.
    if len(out) >= 2 and abs((out[0] + 2 * pi) - out[-1]) <= tol:
        out.pop()
    return out


def _norm_angle(a: float) -> float:
    x = a % (2 * pi)
    if x < 0:
        x += 2 * pi
    return x


def _interior_wedge(p: Tuple[float, float], eps: float = 1e-9) -> Tuple[float, float]:
    """
    Return (start_angle, width) for the inside of the unit square at point p.
    width is one of {2pi, pi, pi/2}.
    """
    x, y = p
    on_l = abs(x - 0.0) <= eps
    on_r = abs(x - 1.0) <= eps
    on_b = abs(y - 0.0) <= eps
    on_t = abs(y - 1.0) <= eps

    # corners
    if on_l and on_b:
        return (0.0, pi / 2)          # [0, 90]
    if on_r and on_b:
        return (pi / 2, pi / 2)       # [90, 180]
    if on_r and on_t:
        return (pi, pi / 2)           # [180, 270]
    if on_l and on_t:
        return (3 * pi / 2, pi / 2)   # [270, 360]

    # edges
    if on_b:
        return (0.0, pi)              # [0, 180]
    if on_t:
        return (pi, pi)               # [180, 360]
    if on_l:
        return (3 * pi / 2, pi)       # [270, 450] == [-90, 90]
    if on_r:
        return (pi / 2, pi)           # [90, 270]

    # interior
    return (0.0, 2 * pi)


def _wedge_param(a: float, start: float) -> float:
    return _norm_angle(a - start)


def corner_sectors(g: CreaseGraph, v_idx: int) -> List[float]:
    """
    Sector angles for corner condition inside the paper interior wedge.
    """
    p = g.vertices[v_idx]
    start, width = _interior_wedge(p, eps=g.eps)
    angs = unique_angles(incident_angles(g, v_idx, include_boundary=False))

    ts: List[float] = [0.0, width]
    for a in angs:
        t = _wedge_param(a, start)
        if -1e-9 <= t <= width + 1e-9:
            ts.append(min(max(t, 0.0), width))

    ts = sorted(unique_angles(ts, tol=1e-8))
    if not ts:
        return []

    if width >= 2 * pi - 1e-8:
        out = []
        for i in range(len(ts)):
            a = ts[i]
            b = ts[(i + 1) % len(ts)]
            d = b - a
            if d <= 0:
                d += 2 * pi
            out.append(d)
        return out

    out: List[float] = []
    for i in range(len(ts) - 1):
        out.append(ts[i + 1] - ts[i])
    return out


def sector_angles(angles: Sequence[float]) -> List[float]:
    if not angles:
        return []
    out = []
    for i in range(len(angles)):
        a = angles[i]
        b = angles[(i + 1) % len(angles)]
        d = b - a
        if d <= 0:
            d += 2 * pi
        out.append(d)
    return out


def kawasaki_residual(g: CreaseGraph, v_idx: int) -> float:
    angs = unique_angles(incident_angles(g, v_idx))
    if len(angs) < 4 or len(angs) % 2 != 0:
        return float("inf")
    secs = sector_angles(angs)
    odd_sum = sum(secs[::2])
    even_sum = sum(secs[1::2])
    return abs(odd_sum - pi) + abs(even_sum - pi)


def corner_condition_ok(g: CreaseGraph, v_idx: int) -> bool:
    secs = corner_sectors(g, v_idx)
    if not secs:
        return True
    # Strict corner condition: every sector must be strictly less than corner_max_deg.
    thr = corner_threshold_rad()
    return all(s < thr for s in secs)


def corner_condition_error(g: CreaseGraph, v_idx: int) -> float:
    """
    0 means corner condition is satisfied (all sectors < corner_max_deg).
    Positive value is the total amount exceeding corner_max_deg.
    """
    secs = corner_sectors(g, v_idx)
    if not secs:
        return 0.0
    thr = corner_threshold_rad()
    return sum(max(0.0, s - thr) for s in secs)


def corner_max_sector(g: CreaseGraph, v_idx: int) -> float:
    secs = corner_sectors(g, v_idx)
    if not secs:
        return 0.0
    return max(secs) if secs else 0.0


def is_interior_point(p: Tuple[float, float], eps: float = 1e-9) -> bool:
    x, y = p
    return eps < x < 1.0 - eps and eps < y < 1.0 - eps


def vertex_kawasaki_error(g: CreaseGraph, v_idx: int) -> float:
    """
    0 means satisfied. Positive means violation.
    For invalid degree patterns (odd or <4), return a large penalty.
    """
    angs = unique_angles(incident_angles(g, v_idx))
    deg = len(angs)
    if deg < 4 or deg % 2 != 0:
        return 10.0 + float(abs(deg - 4))
    return kawasaki_residual(g, v_idx)


def interior_vertex_ids(g: CreaseGraph) -> List[int]:
    return [i for i, p in enumerate(g.vertices) if is_interior_point(p, eps=g.eps)]


def kawasaki_all_interior_ok(g: CreaseGraph, tol: float = 1e-6) -> bool:
    for v in interior_vertex_ids(g):
        if vertex_kawasaki_error(g, v) > tol:
            return False
    return True


def used_dir_indices(g: CreaseGraph, v_idx: int) -> Set[int]:
    """
    Quantize existing incident edge directions at v_idx to the 16-direction index set.
    """
    vx, vy = g.vertices[v_idx]
    used: Set[int] = set()
    for i, j in g.edges:
        e = (i, j) if i < j else (j, i)
        if e in g.boundary_edges:
            continue
        if i != v_idx and j != v_idx:
            continue
        u = j if i == v_idx else i
        ux, uy = g.vertices[u]
        dx, dy = ux - vx, uy - vy
        if abs(dx) < EPS and abs(dy) < EPS:
            continue
        best_k = 0
        best_dot = -1e100
        for k, (rx, ry) in enumerate(DIRS):
            d = dx * rx + dy * ry
            if d > best_dot:
                best_dot = d
                best_k = k
        used.add(best_k)
    return used


def total_edge_length(g: CreaseGraph) -> float:
    total = 0.0
    for i, j in g.edges:
        x1, y1 = g.vertices[i]
        x2, y2 = g.vertices[j]
        dx = x2 - x1
        dy = y2 - y1
        total += (dx * dx + dy * dy) ** 0.5
    return total


def global_constraint_score(
    g: CreaseGraph,
    corner_ids: Sequence[int],
    tol: float = 1e-6,
) -> Tuple[int, int, float, float, int, float]:
    """
    Lexicographic score:
    1) fewer corner-condition violations at initial corners,
    2) fewer Kawasaki violations at interior vertices,
    3) smaller total corner error,
    4) smaller total Kawasaki error.
    """
    bad_corner = 0
    total_corner = 0.0
    for v in corner_ids:
        err = corner_condition_error(g, v)
        total_corner += err
        if not corner_condition_ok(g, v):
            bad_corner += 1

    bad_k = 0
    total_k = 0.0
    for v in interior_vertex_ids(g):
        err = vertex_kawasaki_error(g, v)
        total_k += err
        if err > tol:
            bad_k += 1
    return (bad_corner, bad_k, total_corner, total_k, len(g.edges), total_edge_length(g))


def find_vertex_idx(g: CreaseGraph, p: Tuple[float, float], tol: float = 1e-8) -> Optional[int]:
    px, py = p
    for i, q in enumerate(g.vertices):
        if abs(px - q[0]) <= tol and abs(py - q[1]) <= tol:
            return i
    return None


def mirror_point_y_eq_x(p: Tuple[float, float]) -> Tuple[float, float]:
    return (p[1], p[0])


def _point_on_line(a: Tuple[float, float], b: Tuple[float, float], p: Tuple[float, float], tol: float) -> bool:
    abx, aby = b[0] - a[0], b[1] - a[1]
    apx, apy = p[0] - a[0], p[1] - a[1]
    # cross near 0 -> collinear
    return abs(cross(abx, aby, apx, apy)) <= tol


def _has_collinear_path(
    g: CreaseGraph,
    start_idx: int,
    goal_idx: int,
    tol: float = 1e-8,
) -> bool:
    """
    True if start and goal are connected by a polyline that stays on the same
    geometric line (allows different edge subdivision).
    """
    if start_idx == goal_idx:
        return True
    a = g.vertices[start_idx]
    b = g.vertices[goal_idx]
    stack = [start_idx]
    seen: Set[int] = {start_idx}
    while stack:
        u = stack.pop()
        if u == goal_idx:
            return True
        for i, j in g.edges:
            if i != u and j != u:
                continue
            v = j if i == u else i
            if v in seen:
                continue
            pv = g.vertices[v]
            if not _point_on_line(a, b, pv, tol):
                continue
            seen.add(v)
            stack.append(v)
    return False


def diagonal_symmetry_ok(g: CreaseGraph, tol: float = 1e-8) -> bool:
    """
    Check y=x symmetry of the current crease graph.
    """
    for i, j in g.edges:
        pi = g.vertices[i]
        pj = g.vertices[j]
        mi = find_vertex_idx(g, mirror_point_y_eq_x(pi), tol=tol)
        mj = find_vertex_idx(g, mirror_point_y_eq_x(pj), tol=tol)
        if mi is None or mj is None:
            return False
        e = (mi, mj) if mi < mj else (mj, mi)
        if e in g.edges:
            continue
        # Accept different segment subdivision along the same mirrored line.
        if not _has_collinear_path(g, mi, mj, tol=tol):
            return False
    return True


def mirrored_dir_idx(dir_idx: int) -> int:
    # Reflection across y=x maps angle index k to (4-k) mod 16.
    return (4 - dir_idx) % ANGLE_COUNT


def apply_ray_action(
    g: CreaseGraph,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool = True,
    symmetry_tol: float = 1e-8,
) -> Optional[CreaseGraph]:
    """
    One additive action for search:
    - shoot one ray from (v_idx, dir_idx),
    - optionally shoot mirrored ray to preserve y=x symmetry.
    """
    h = clone_graph(g)
    if h.shoot_ray_and_split(v_idx, dir_idx) is None:
        return None

    if enforce_symmetry:
        p = g.vertices[v_idx]
        mv = find_vertex_idx(h, mirror_point_y_eq_x(p), tol=symmetry_tol)
        if mv is None:
            return None
        md = mirrored_dir_idx(dir_idx)
        # Avoid duplicate second shot when action is self-mirrored.
        if not (mv == v_idx and md == dir_idx):
            if h.shoot_ray_and_split(mv, md) is None:
                return None
        if not diagonal_symmetry_ok(h, tol=symmetry_tol):
            return None
    return h


def graph_state_key(g: CreaseGraph, ndigits: int = 8) -> Tuple:
    """
    Hashable canonical-ish key for visited-state pruning.
    """
    coords = tuple((round(p[0], ndigits), round(p[1], ndigits)) for p in g.vertices)
    edge_coords = []
    for i, j in g.edges:
        a = coords[i]
        b = coords[j]
        edge_coords.append((a, b) if a <= b else (b, a))
    edge_coords.sort()
    return tuple(edge_coords)


def violating_vertex_priority(
    g: CreaseGraph,
    corner_ids: Sequence[int],
    tol: float,
) -> List[int]:
    violating_set: Set[int] = set(v for v in corner_ids if not corner_condition_ok(g, v))
    violating_set.update(v for v in interior_vertex_ids(g) if vertex_kawasaki_error(g, v) > tol)
    return sorted(
        list(violating_set),
        key=lambda v: (
            0 if v in corner_ids else 1,
            -(corner_condition_error(g, v) + vertex_kawasaki_error(g, v)),
        ),
    )


def clone_graph(g: CreaseGraph) -> CreaseGraph:
    h = CreaseGraph(eps=g.eps)
    h.vertices = list(g.vertices)
    h.edges = set(g.edges)
    h.boundary_edges = set(g.boundary_edges)
    return h


def beam_search_repair(
    g: CreaseGraph,
    corner_ids: Sequence[int],
    max_steps: int = 120,
    beam_width: int = 80,
    branch_per_state: int = 24,
    tol: float = 1e-6,
    enforce_symmetry: bool = True,
    soft_error_margin: float = 0.25,
) -> CreaseGraph:
    """
    Additive-only search with backtracking:
    - each expansion adds one ray action (and mirrored ray if enabled),
    - keep best `beam_width` states at every depth.
    """
    start = clone_graph(g)
    best_graph = start
    best_score = global_constraint_score(start, corner_ids=corner_ids, tol=tol)
    frontier: List[CreaseGraph] = [start]
    visited: Set[Tuple] = {graph_state_key(start)}

    for _ in range(max_steps):
        scored_frontier = [
            (global_constraint_score(s, corner_ids=corner_ids, tol=tol), s) for s in frontier
        ]
        scored_frontier.sort(key=lambda x: x[0])
        if scored_frontier[0][0][0] == 0 and scored_frontier[0][0][1] == 0:
            return scored_frontier[0][1]

        if scored_frontier[0][0] < best_score:
            best_score = scored_frontier[0][0]
            best_graph = scored_frontier[0][1]

        next_states: List[Tuple[Tuple[int, int, float, float, int, float], CreaseGraph]] = []
        for base_score, state in scored_frontier:
            priority = violating_vertex_priority(state, corner_ids=corner_ids, tol=tol)
            local_children: List[Tuple[Tuple[int, int, float, float, int, float], CreaseGraph]] = []
            for v in priority[:6]:
                used = used_dir_indices(state, v)
                for d in range(ANGLE_COUNT):
                    if d in used:
                        continue
                    child = apply_ray_action(
                        state,
                        v_idx=v,
                        dir_idx=d,
                        enforce_symmetry=enforce_symmetry,
                    )
                    if child is None:
                        continue
                    k = graph_state_key(child)
                    if k in visited:
                        continue
                    score = global_constraint_score(child, corner_ids=corner_ids, tol=tol)
                    # Phase 1: while any initial-corner violation exists, force corner improvement.
                    if base_score[0] > 0:
                        if score[0] > base_score[0]:
                            continue
                        if score[0] == base_score[0] and score[2] >= base_score[2] - 1e-12:
                            continue
                    else:
                        # Phase 2: corner is currently satisfied. Allow temporary corner violations;
                        # otherwise the search cannot add the 2nd/3rd rays at a vertex.
                        if score[0] > base_score[0] + 2:
                            continue
                        # Allow temporary increase in violating-vertex count to escape local traps.
                        if score[1] > base_score[1] + 4:
                            continue
                        # Total Kawasaki error should not drift too far upward.
                        if score[3] > base_score[3] + soft_error_margin:
                            continue
                    local_children.append((score, child))
            local_children.sort(key=lambda x: x[0])
            for score, child in local_children[:branch_per_state]:
                k = graph_state_key(child)
                if k in visited:
                    continue
                visited.add(k)
                next_states.append((score, child))

        if not next_states:
            break
        next_states.sort(key=lambda x: x[0])
        frontier = [s for _, s in next_states[:beam_width]]

    return best_graph


def parse_corners(text: str) -> List[Tuple[float, float]]:
    """
    Parse "x1,y1;x2,y2;..." into list of points in [0,1]^2.
    """
    points: List[Tuple[float, float]] = []
    chunks = [c.strip() for c in text.split(";") if c.strip()]
    if not chunks:
        raise ValueError("corners is empty")

    for chunk in chunks:
        xy = [t.strip() for t in chunk.split(",")]
        if len(xy) != 2:
            raise ValueError(f"invalid corner format: {chunk}")
        x = float(xy[0])
        y = float(xy[1])
        if not in_square((x, y)):
            raise ValueError(f"corner out of [0,1]^2: {(x, y)}")
        points.append((x, y))

    return points


def corners_diag_symmetric(corners: Sequence[Tuple[float, float]], tol: float = 1e-8) -> bool:
    """
    Return True if the corner set is symmetric with respect to y=x.
    """
    for p in corners:
        q = mirror_point_y_eq_x(p)
        found = any(abs(q[0] - r[0]) <= tol and abs(q[1] - r[1]) <= tol for r in corners)
        if not found:
            return False
    return True


def build_pattern(
    corners: Sequence[Tuple[float, float]],
    depth: int = 2,
    max_lines_per_iter: int = 2000,
    corner_dirs: Optional[Sequence[Sequence[int]]] = None,
    search_max_steps: int = 120,
    beam_width: int = 80,
    branch_per_state: int = 24,
    kawasaki_tol: float = 1e-6,
    enforce_symmetry: bool = True,
    soft_error_margin: float = 0.25,
) -> Tuple[CreaseGraph, List[Tuple[float, float]], List[int]]:
    if enforce_symmetry and not corners_diag_symmetric(corners):
        raise ValueError("enforce_symmetry=True requires corners to be y=x symmetric")

    candidates = enumerate_candidate_vertices(
        corners,
        depth=depth,
        max_lines_per_iter=max_lines_per_iter,
    )

    g = CreaseGraph()
    g.init_square_boundary()
    corner_ids = [g.add_vertex(p) for p in corners]

    # Initial rays from corners (not necessarily all 16 directions).
    if corner_dirs is None:
        corner_dirs = [[] for _ in corner_ids]
    if len(corner_dirs) != len(corner_ids):
        raise ValueError("corner_dirs length must match number of corners")

    for v, dirs in zip(corner_ids, corner_dirs):
        for d in dirs:
            if not (0 <= d < ANGLE_COUNT):
                raise ValueError(f"direction index out of range: {d}")
            seeded = apply_ray_action(
                g,
                v_idx=v,
                dir_idx=d,
                enforce_symmetry=enforce_symmetry,
            )
            if seeded is not None:
                g = seeded

    # Add rays via additive-only beam search.
    g = beam_search_repair(
        g,
        corner_ids=corner_ids,
        max_steps=search_max_steps,
        beam_width=beam_width,
        branch_per_state=branch_per_state,
        tol=kawasaki_tol,
        enforce_symmetry=enforce_symmetry,
        soft_error_margin=soft_error_margin,
    )

    return g, candidates, corner_ids


def render_pattern(
    graph: CreaseGraph,
    corners: Sequence[Tuple[float, float]],
    candidates: Optional[Sequence[Tuple[float, float]]] = None,
    out_path: str = "crease.png",
    show: bool = True,
) -> None:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 6), dpi=140)

    for i, j in graph.edges:
        x1, y1 = graph.vertices[i]
        x2, y2 = graph.vertices[j]
        ax.plot([x1, x2], [y1, y2], color="black", linewidth=1.2)

    if candidates:
        cx = [p[0] for p in candidates]
        cy = [p[1] for p in candidates]
        ax.scatter(cx, cy, s=8, color="#3a86ff", alpha=0.35, label="candidates")

    if corners:
        kx = [p[0] for p in corners]
        ky = [p[1] for p in corners]
        ax.scatter(kx, ky, s=38, color="#e63946", label="corners", zorder=4)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Generated Crease Pattern")
    ax.grid(alpha=0.2)
    ax.legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    if show:
        plt.show()
    plt.close(fig)


def run(
    corners: Sequence[Tuple[float, float]],
    depth: int = 2,
    max_lines_per_iter: int = 2000,
    out_path: str = "crease.png",
    show: bool = True,
    corner_dirs: Optional[Sequence[Sequence[int]]] = None,
    search_max_steps: int = 120,
    beam_width: int = 80,
    branch_per_state: int = 24,
    kawasaki_tol: float = 1e-6,
    enforce_symmetry: bool = True,
    soft_error_margin: float = 0.25,
    render_image: bool = True,
    corner_max_deg: float = 90.0,
) -> None:
    set_corner_max_deg(corner_max_deg)

    graph, candidates, corner_ids = build_pattern(
        corners,
        depth=depth,
        max_lines_per_iter=max_lines_per_iter,
        corner_dirs=corner_dirs,
        search_max_steps=search_max_steps,
        beam_width=beam_width,
        branch_per_state=branch_per_state,
        kawasaki_tol=kawasaki_tol,
        enforce_symmetry=enforce_symmetry,
        soft_error_margin=soft_error_margin,
    )

    print(f"[Stage1] candidate vertices: {len(candidates)}")
    print(f"[Stage2] vertices={len(graph.vertices)} edges={len(graph.edges)}")

    for v in corner_ids:
        uniq_deg = len(unique_angles(incident_angles(graph, v)))
        used_dirs = len(used_dir_indices(graph, v))
        print(
            f"v={v} kawasaki_residual={kawasaki_residual(graph, v):.6f} "
            f"corner_ok={corner_condition_ok(graph, v)} "
            f"max_sector_deg={corner_max_sector(graph, v) * 180.0 / pi:.2f} "
            f"uniq_deg={uniq_deg} "
            f"used_dirs={used_dirs}"
        )
    print(
        "[Kawasaki interior]",
        "OK" if kawasaki_all_interior_ok(graph, tol=kawasaki_tol) else "NOT SATISFIED",
    )
    corner_ok_all = all(corner_condition_ok(graph, v) for v in corner_ids)
    print(
        f"[Corner condition @initial corners] (threshold<{corner_max_deg}deg)",
        "OK" if corner_ok_all else "NOT SATISFIED",
    )
    print("[Diagonal symmetry y=x]", "OK" if diagonal_symmetry_ok(graph) else "NOT SATISFIED")

    if render_image:
        render_pattern(
            graph=graph,
            corners=corners,
            candidates=candidates,
            out_path=out_path,
            show=show,
        )
        print(f"[Output] image saved: {out_path}")
    else:
        print("[Output] image rendering skipped")


def main() -> None:
    # Copy-paste friendly settings (Colab/local)
    r2 = 2**0.5
    corners = [
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0 / r2, 1.0 / r2),
    ]
    # For each corner, specify initial 16-direction indices to shoot.
    # 0=0deg, 1=22.5deg, ..., 15=337.5deg
    # Empty list is allowed (then repair step decides what to add).
    # This is only an initial seed, not a mandatory complete set.
    corner_dirs = [
        [],
        [],
        [],
    ]
    depth = 1
    max_lines_per_iter = 2000
    out_path = "crease.png"
    show = False
    search_max_steps = 180
    beam_width = 120
    branch_per_state = 32
    kawasaki_tol = 1e-6
    enforce_symmetry = False
    soft_error_margin = 0.25
    render_image = True
    # Tighten corner condition by lowering this value (e.g. 67.5, 45.0).
    corner_max_deg = 67.5

    run(
        corners=corners,
        depth=depth,
        max_lines_per_iter=max_lines_per_iter,
        out_path=out_path,
        show=show,
        corner_dirs=corner_dirs,
        search_max_steps=search_max_steps,
        beam_width=beam_width,
        branch_per_state=branch_per_state,
        kawasaki_tol=kawasaki_tol,
        enforce_symmetry=enforce_symmetry,
        soft_error_margin=soft_error_margin,
        render_image=render_image,
        corner_max_deg=corner_max_deg,
    )


if __name__ == "__main__":
    main()
