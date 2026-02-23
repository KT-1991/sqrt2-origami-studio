from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


def single_ray_growth_probe(
    g,
    origin_v: int,
    dir_idx: int,
    *,
    point_key,
    required_grid_bounds_for_point,
) -> Tuple[bool, int, Optional[Tuple[int, int, int]]]:
    # Returns (usable, growth_class, req_bounds)
    # growth_class: 0 no vertex increase, 1 increase within current grid, 2 requires finer grid
    hit = g.ray_hit_at(origin_v, dir_idx)
    if hit is None:
        return (False, 2, None)
    _, _, hit_pos, p = hit
    if hit_pos != 0:
        return (True, 0, None)
    hit_v = g.point_to_id.get(point_key(p))
    if hit_v is None:
        return (True, 2, required_grid_bounds_for_point(p))
    if hit_v in g.active_vertices:
        return (True, 0, None)
    return (True, 1, None)


def move_growth_probe(
    g,
    v_idx: int,
    dir_idx: int,
    enforce_symmetry: bool,
    *,
    single_ray_growth_probe_fn,
    mirrored_dir_idx,
) -> Tuple[bool, int, Optional[Tuple[int, int, int]]]:
    usable, grow, req = single_ray_growth_probe_fn(g, v_idx, dir_idx)
    if not usable:
        return (False, 2, None)
    if not enforce_symmetry:
        return (True, grow, req)
    mv = g.mirror_vertex_idx(v_idx)
    if mv is None:
        return (False, 2, None)
    md = mirrored_dir_idx(dir_idx)
    musable, mgrow, mreq = single_ray_growth_probe_fn(g, mv, md)
    if not musable:
        return (False, 2, None)
    out_req = req
    if mreq is not None:
        if out_req is None:
            out_req = mreq
        else:
            out_req = (max(out_req[0], mreq[0]), max(out_req[1], mreq[1]), max(out_req[2], mreq[2]))
    return (True, max(grow, mgrow), out_req)


def best_expand_move_for_corner(
    g,
    v_idx: int,
    enforce_symmetry: bool,
    *,
    used_dir_indices_fn,
    admissible_dirs_for_vertex,
    move_growth_probe_fn,
    required_norm_bounds_from_grid_bounds,
) -> Optional[Tuple[int, int, int, int, int, int]]:
    # Returns (dir_idx, need_a, need_b, need_k, need_a_norm, need_b_norm)
    if v_idx not in g.active_vertices:
        return None
    used = used_dir_indices_fn(g, v_idx, include_boundary=False)
    admissible = admissible_dirs_for_vertex(g, v_idx, enforce_symmetry=enforce_symmetry)
    best_key: Optional[Tuple[int, int, int, int, int, int, int, int]] = None
    best_out: Optional[Tuple[int, int, int, int, int, int]] = None
    for d in admissible:
        if d in used:
            continue
        usable, grow, req = move_growth_probe_fn(g, v_idx=v_idx, dir_idx=d, enforce_symmetry=enforce_symmetry)
        if (not usable) or grow <= 1 or req is None:
            continue
        ran, rbn = required_norm_bounds_from_grid_bounds(req[0], req[1], req[2])
        key = (req[2], max(ran, rbn), ran + rbn, max(req[0], req[1]), req[0] + req[1], req[0], req[1], d)
        if best_key is None or key < best_key:
            best_key = key
            best_out = (d, req[0], req[1], req[2], ran, rbn)
    return best_out


def grid_required_corner_expand_request(
    g,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int,
    enforce_symmetry: bool,
    *,
    corner_condition_error,
    corner_line_count,
    used_dir_indices_fn,
    admissible_dirs_for_vertex,
    move_growth_probe_fn,
    required_norm_bounds_from_grid_bounds,
) -> Optional[Tuple[int, int, int, int, int, int, int, int]]:
    # Returns minimal required expansion from one grid-required corner:
    # (need_a, need_b, need_k, need_a_norm, need_b_norm, required_corner_count, representative_corner_id, representative_dir)
    # Prefer corners that have no non-expanding move, but if none exist,
    # allow corners that still need expansion for some directions.
    required: List[Tuple[int, int, int, int, int, int, int, int]] = []
    for v in corner_ids:
        if v not in g.active_vertices:
            continue
        need_corner = corner_condition_error(g, v, max_deg=max_deg) > 1e-12
        need_lines = corner_line_count(g, v) < min_corner_lines
        if (not need_corner) and (not need_lines):
            continue
        used = used_dir_indices_fn(g, v, include_boundary=False)
        admissible = admissible_dirs_for_vertex(g, v, enforce_symmetry=enforce_symmetry)
        has_nonexpand_move = False
        reqs: List[Tuple[int, int, int, int, int, int]] = []
        for d in admissible:
            if d in used:
                continue
            usable, grow, req = move_growth_probe_fn(g, v_idx=v, dir_idx=d, enforce_symmetry=enforce_symmetry)
            if not usable:
                continue
            if grow <= 1:
                has_nonexpand_move = True
                continue
            if req is not None:
                ran, rbn = required_norm_bounds_from_grid_bounds(req[0], req[1], req[2])
                reqs.append((req[0], req[1], req[2], ran, rbn, d))
        if not reqs:
            continue
        best_req = min(
            reqs,
            key=lambda t: (t[2], max(t[3], t[4]), t[3] + t[4], max(t[0], t[1]), t[0] + t[1], t[0], t[1], t[5]),
        )
        required.append((v, best_req[0], best_req[1], best_req[2], best_req[3], best_req[4], 1 if has_nonexpand_move else 0, best_req[5]))

    if not required:
        return None
    best_v, ra, rb, rk, ran, rbn, has_nonexpand, best_d = min(
        required,
        key=lambda x: (x[6], x[3], max(x[4], x[5]), x[4] + x[5], max(x[1], x[2]), x[1] + x[2], x[1], x[2], x[0], x[7]),
    )
    _ = has_nonexpand
    return (ra, rb, rk, ran, rbn, len(required), best_v, best_d)
