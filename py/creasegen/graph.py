from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from creasegen.core_types import (
    ANGLE_COUNT,
    DIRS,
    DIRS_F,
    DIRS_I,
    ONE,
    PointE,
    Q2Int,
    Qsqrt2,
    ZERO,
    ZERO_I,
    _q2_cmp,
    _q2_cmp_int,
    _q2_cross_int,
    _q2_div_int_to_q2,
    _q2_neg_int,
    _q2_sign_aligned,
    _q2_sub_int,
    _q2_to_int,
)
from creasegen.direction import _angle_of_dir_idx, _nearest_dir_idx
from creasegen.geometry import _collinear_overlap_length, _ray_segment_hit_t_float
from creasegen.grid_utils import (
    _MASK64,
    _edge_hash_pair,
    _point_key,
    _record_missing_point_stats,
)

def _cross(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2) -> Qsqrt2:
    return ax * by - ay * bx


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
        self.edge_scan_cache_version: int = -1
        self.edge_scan_cache: Dict[int, Tuple[Tuple[int, int], ...]] = {}
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
        self.edge_version: int = 0

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

    def _add_edge_raw(
        self,
        i: int,
        j: int,
        boundary: bool,
        birth: Optional[int],
        invalidate_face: bool = True,
    ) -> None:
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
        self.edge_version += 1
        if invalidate_face:
            self._invalidate_face_cache()

    def _remove_edge_raw(self, i: int, j: int, invalidate_face: bool = True) -> None:
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
        self.edge_version += 1
        if invalidate_face:
            self._invalidate_face_cache()

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

    def _invalidate_face_cache(self) -> None:
        # Face index was removed after global hit strategy unification.
        # Kept as a no-op to preserve method contracts at call sites.
        return

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

    def _edge_candidates_for_dir(self, dir_idx: int) -> Tuple[Tuple[int, int], ...]:
        if self.edge_scan_cache_version != self.edge_version:
            self.edge_scan_cache.clear()
            self.edge_scan_cache_version = self.edge_version
        out = self.edge_scan_cache.get(dir_idx)
        if out is not None:
            return out
        blocked = dir_idx % (ANGLE_COUNT // 2)
        cands: List[Tuple[int, int]] = []
        for b, eset in enumerate(self.edge_parallel_buckets):
            if b == blocked:
                continue
            cands.extend(eset)
        cands.extend(self.edge_unknown_dir)
        out = tuple(cands)
        self.edge_scan_cache[dir_idx] = out
        return out

    def _iter_edges_for_ray_dir(self, dir_idx: int):
        yield from self._edge_candidates_for_dir(dir_idx)

    def add_vertex(self, p: PointE) -> int:
        key = _point_key(p)
        if key not in self.point_to_id:
            raise ValueError(f"point not found in pre-enumerated grid: {p.approx()}")
        v = self.point_to_id[key]
        self.activate_vertex(v)
        return v

    def add_edge(
        self,
        i: int,
        j: int,
        boundary: bool = False,
        mark_ray_dirty: bool = True,
        invalidate_face: bool = True,
    ) -> None:
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
        self._add_edge_raw(i, j, boundary=boundary, birth=None, invalidate_face=invalidate_face)
        if mark_ray_dirty:
            self._mark_ray_dirty_after_change([e])

    def remove_edge(self, i: int, j: int, mark_ray_dirty: bool = True, invalidate_face: bool = True) -> None:
        e = self._norm_edge(i, j)
        if e not in self.edges:
            return
        was_boundary = e in self.boundary_edges
        old_birth = self.edge_birth.get(e)
        self._tx_record("RESTORE_EDGE_RAW", e[0], e[1], was_boundary, old_birth)
        self._remove_edge_raw(i, j, invalidate_face=invalidate_face)
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
        points_f = self.points_f
        ray_hit_t = _ray_segment_hit_t_float
        origin_f = points_f[v]
        row: List[Optional[int]] = [None] * ANGLE_COUNT
        row_hit: List[Optional[Tuple[int, int, int, PointE]]] = [None] * ANGLE_COUNT
        tol = 1e-9
        for d in range(ANGLE_COUNT):
            d_f = DIRS_F[d]
            d_i = DIRS_I[d]
            dx_f, dy_f = d_f
            origin_proj = origin_f[0] * dx_f + origin_f[1] * dy_f
            best_t_f: Optional[float] = None
            shortlist: List[Tuple[float, int, int]] = []
            for i, j in self._iter_edges_for_ray_dir(d):
                pi = points_f[i]
                pj = points_f[j]
                if (pi[0] * dx_f + pi[1] * dy_f) <= origin_proj + 1e-12 and (
                    pj[0] * dx_f + pj[1] * dy_f
                ) <= origin_proj + 1e-12:
                    continue
                t_f = ray_hit_t(origin_f, d_f, pi, pj, eps=1e-12)
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
            if len(shortlist) > 1:
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

    def _first_hit_edge_from_candidates(
        self,
        origin_v: int,
        dir_idx: int,
        candidates: Iterable[Tuple[int, int]],
    ) -> Optional[Tuple[Qsqrt2, int, int, int, PointE]]:
        points_f = self.points_f
        ray_hit_t = _ray_segment_hit_t_float
        origin_f = points_f[origin_v]
        d_f = DIRS_F[dir_idx]
        dx_f, dy_f = d_f
        origin_proj = origin_f[0] * dx_f + origin_f[1] * dy_f
        d_i = DIRS_I[dir_idx]
        origin = self.points[origin_v]
        origin_i = self._point_int_pair(origin_v)

        best_t_f: Optional[float] = None
        shortlist: List[Tuple[float, int, int]] = []
        tol = 1e-9
        for i, j in candidates:
            pi = points_f[i]
            pj = points_f[j]
            if (pi[0] * dx_f + pi[1] * dy_f) <= origin_proj + 1e-12 and (
                pj[0] * dx_f + pj[1] * dy_f
            ) <= origin_proj + 1e-12:
                continue
            t_f = ray_hit_t(origin_f, d_f, pi, pj, eps=1e-12)
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
        best: Optional[Tuple[Qsqrt2, int, int, int, PointE]] = None
        if len(shortlist) > 1:
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
                best = (t, i, j, hit_pos, p)
        return best

    def _first_hit_edge_global(self, origin_v: int, dir_idx: int) -> Optional[Tuple[Qsqrt2, int, int, int, PointE]]:
        return self._first_hit_edge_from_candidates(
            origin_v,
            dir_idx,
            self._iter_edges_for_ray_dir(dir_idx),
        )

    def first_hit_edge(self, origin_v: int, dir_idx: int) -> Optional[Tuple[int, int, int, PointE]]:
        # Fast path: reuse cached exact hit when this vertex is already clean.
        if origin_v in self.active_vertices and origin_v not in self.ray_dirty:
            row = self.ray_hit.get(origin_v)
            if row is not None:
                return row[dir_idx]
        # Single deterministic strategy: global candidate scan only.
        hit = self._first_hit_edge_global(origin_v, dir_idx)
        if hit is None:
            return None
        _, i, j, hit_pos, p = hit
        return (i, j, hit_pos, p)

    def shoot_ray_and_split(
        self,
        origin_v: int,
        dir_idx: int,
        known_hit: Optional[Tuple[int, int, int, PointE]] = None,
        stats: Optional[Dict[str, int]] = None,
    ) -> Optional[Tuple[int, int]]:
        if origin_v not in self.active_vertices:
            return None
        hit = known_hit if known_hit is not None else self.first_hit_edge(origin_v, dir_idx)
        if hit is None:
            return None
        i, j, hit_pos, p = hit
        old_e = self._norm_edge(i, j)
        was_boundary = old_e in self.boundary_edges
        changed_edges: List[Tuple[int, int]] = []
        batched_face_invalidate = hit_pos == 0
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
            self.remove_edge(i, j, mark_ray_dirty=False, invalidate_face=not batched_face_invalidate)
            changed_edges.append(old_e)
            self.add_edge(
                i,
                hit_v,
                boundary=was_boundary,
                mark_ray_dirty=False,
                invalidate_face=not batched_face_invalidate,
            )
            self.add_edge(
                hit_v,
                j,
                boundary=was_boundary,
                mark_ray_dirty=False,
                invalidate_face=not batched_face_invalidate,
            )
            changed_edges.append(self._norm_edge(i, hit_v))
            changed_edges.append(self._norm_edge(hit_v, j))
        self.add_edge(
            origin_v,
            hit_v,
            boundary=False,
            mark_ray_dirty=False,
            invalidate_face=not batched_face_invalidate,
        )
        changed_edges.append(self._norm_edge(origin_v, hit_v))
        if batched_face_invalidate:
            self._invalidate_face_cache()
        self._mark_ray_dirty_after_change(changed_edges)
        return (origin_v, hit_v)
