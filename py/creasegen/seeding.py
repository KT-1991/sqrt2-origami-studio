from __future__ import annotations

from math import pi
from typing import Dict, List, Optional, Sequence, Set, Tuple

from creasegen.core_types import ANGLE_COUNT, DIRS, ZERO, _q2_sign


def exact_dir_idx_from_delta(dx, dy) -> Optional[int]:
    for k, (rx, ry) in enumerate(DIRS):
        c = dx * ry - dy * rx
        if c != ZERO:
            continue
        d = dx * rx + dy * ry
        s = _q2_sign(d)
        if s > 0:
            return k
        if s < 0:
            return (k + ANGLE_COUNT // 2) % ANGLE_COUNT
    return None


def is_aligned_with_16_dirs(p, q) -> bool:
    dx = q.x - p.x
    dy = q.y - p.y
    if dx == ZERO and dy == ZERO:
        return False
    for rx, ry in DIRS:
        if dx * ry - dy * rx == ZERO:
            return True
    return False


def used_dir_indices(
    g,
    v_idx: int,
    *,
    edge_dir_from,
    include_boundary: bool = False,
) -> Set[int]:
    out: Set[int] = set()
    for u in g.adj.get(v_idx, set()):
        e = (v_idx, u) if v_idx < u else (u, v_idx)
        if not include_boundary and e in g.boundary_edges:
            continue
        d = edge_dir_from(g, v_idx, u)
        if d is not None:
            out.add(d)
    return out


def corner_condition_error_with_added_dir(
    g,
    v_idx: int,
    dir_idx: int,
    max_deg: float,
    *,
    interior_wedge,
    norm_angle,
    incident_angles,
    unique_angles,
    angle_of_dir_idx,
) -> float:
    px, py = g.points_f[v_idx]
    start, width = interior_wedge(px, py)
    angs = unique_angles(incident_angles(g, v_idx, include_boundary=False))
    a = angle_of_dir_idx(dir_idx)
    t = norm_angle(a - start)
    if -1e-12 <= t <= width + 1e-12:
        angs = unique_angles(sorted(angs + [a]))

    ts: List[float] = [0.0, width]
    for aa in angs:
        tt = norm_angle(aa - start)
        if -1e-12 <= tt <= width + 1e-12:
            ts.append(min(max(tt, 0.0), width))
    ts = unique_angles(sorted(ts))
    secs: List[float] = []
    if len(ts) > 1:
        if width >= 2 * pi - 1e-10:
            for i in range(len(ts)):
                a0 = ts[i]
                b0 = ts[(i + 1) % len(ts)]
                d = b0 - a0
                if d <= 0:
                    d += 2 * pi
                secs.append(d)
        else:
            for i in range(len(ts) - 1):
                secs.append(ts[i + 1] - ts[i])
    thr = max_deg * pi / 180.0
    return sum(max(0.0, s - thr) for s in secs)


def boundary_corner_promising_expand_targets(
    g,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int,
    enforce_symmetry: bool,
    *,
    is_boundary_vertex,
    corner_condition_error,
    corner_line_count,
    required_corner_lines_fn,
    used_dir_indices_fn,
    admissible_dirs_for_vertex,
    corner_condition_error_with_added_dir_fn,
    topk_dirs_for_vertex,
) -> List[int]:
    out: List[int] = []
    for v in corner_ids:
        if v not in g.active_vertices or (not is_boundary_vertex(g, v)):
            continue
        before_err = corner_condition_error(g, v, max_deg=max_deg)
        before_lines = corner_line_count(g, v)
        need_lines = required_corner_lines_fn(
            g,
            v,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
        )
        if before_err <= 1e-12 and before_lines >= need_lines:
            continue

        used = used_dir_indices_fn(g, v, include_boundary=False)
        row_v = g.ensure_ray_next(v)
        feasible: List[int] = []
        first_hit: Dict[int, Optional[int]] = {}
        for d in admissible_dirs_for_vertex(g, v, enforce_symmetry=enforce_symmetry):
            if d in used:
                continue
            hit_v = row_v[d]
            if hit_v is None:
                continue
            line_improve = before_lines < need_lines
            err_after = corner_condition_error_with_added_dir_fn(g, v, d, max_deg=max_deg)
            err_improve = err_after + 1e-12 < before_err
            if not (line_improve or err_improve):
                continue
            feasible.append(d)
            first_hit[d] = hit_v
        if not feasible:
            continue
        check_dirs = topk_dirs_for_vertex(
            g,
            v_idx=v,
            dirs=feasible,
            used_dirs=used,
            k=min(4, len(feasible)),
            first_hit_map=first_hit,
        )
        if check_dirs:
            out.append(v)
    return out


def seed_direct_corner_connections(
    g,
    corner_ids: Sequence[int],
    *,
    is_aligned_with_16_dirs_fn,
    is_square_corner_vertex,
    priority_corner_kawasaki_score,
    kawasaki_score,
    corner_condition_error,
    corner_line_count,
    required_corner_lines_fn,
    is_boundary_vertex,
    clone_graph,
    add_segment_with_splits_ids,
    diagonal_symmetry_ok,
    adopt_graph_state,
    max_deg: float,
    min_corner_lines: int,
    enforce_symmetry: bool = True,
    stats: Optional[Dict[str, int]] = None,
) -> None:
    ids = list(corner_ids)
    kawasaki_tol_seed = 1e-8
    boundary_corner_weight = 0.35

    def _required_lines(h, v_idx: int) -> int:
        return required_corner_lines_fn(
            h,
            v_idx,
            max_deg=max_deg,
            min_corner_lines=min_corner_lines,
        )

    def _corner_unfinished(h, v_idx: int) -> bool:
        if corner_line_count(h, v_idx) < _required_lines(h, v_idx):
            return True
        return corner_condition_error(h, v_idx, max_deg=max_deg) > 1e-12

    def _corner_deficit_total(h) -> float:
        total = 0.0
        for cv in corner_ids:
            deficit = max(0, _required_lines(h, cv) - corner_line_count(h, cv))
            if deficit <= 0:
                continue
            if is_boundary_vertex(h, cv):
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
            if not is_aligned_with_16_dirs_fn(p, q):
                continue
            ux, uy = g.points_f[u]
            vx, vy = g.points_f[v]
            dist2 = (ux - vx) ** 2 + (uy - vy) ** 2
            pairs.append((dist2, u, v))

    # Add shorter corner-corner segments first, allowing split-at-intersections transactions.
    pairs.sort(key=lambda t: t[0])
    attempted_sym_keys: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()
    for _, u, v in pairs:
        if is_square_corner_vertex(g, u) or is_square_corner_vertex(g, v):
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

        endpoint_needed = any(_corner_unfinished(g, vv) for vv in need_vertices)
        endpoint_deficit_before = sum(
            max(0, _required_lines(g, vv) - corner_line_count(g, vv))
            for vv in need_vertices
        )

        trial = clone_graph(g)
        ok = add_segment_with_splits_ids(trial, u, v, max_steps=64, stats=stats)
        if ok and enforce_symmetry and mirror_edge != e:
            ok = add_segment_with_splits_ids(trial, mirror_edge[0], mirror_edge[1], max_steps=64, stats=stats)
        if ok:
            if enforce_symmetry and not diagonal_symmetry_ok(trial):
                continue
            after_ck = priority_corner_kawasaki_score(trial, corner_ids=corner_ids, tol=kawasaki_tol_seed)
            after_k_bad = kawasaki_score(trial, tol=kawasaki_tol_seed)[0]
            after_def = _corner_deficit_total(trial)

            ck_improved = after_ck < before_ck
            deficit_improved = after_def < before_def
            endpoint_deficit_after = sum(
                max(0, _required_lines(trial, vv) - corner_line_count(trial, vv))
                for vv in need_vertices
            )
            endpoint_deficit_improved = endpoint_deficit_after < endpoint_deficit_before
            allow_kawasaki_relax = endpoint_needed and endpoint_deficit_improved

            # Exclude seeds that make interior Kawasaki much worse without line-deficit benefit.
            if after_k_bad > before_k_bad + 1 and not deficit_improved and not allow_kawasaki_relax:
                continue
            # If neither priority-corner Kawasaki nor line deficit improves, skip dense additions.
            if (not ck_improved) and (not deficit_improved) and (not allow_kawasaki_relax):
                continue
            # Do not accept clear degradation on priority-corner Kawasaki unless deficit improves.
            if after_ck > before_ck and not deficit_improved and not allow_kawasaki_relax:
                continue

            adopt_graph_state(g, trial)
