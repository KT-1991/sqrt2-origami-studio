from __future__ import annotations

from typing import Dict, Optional

from creasegen.core_types import ANGLE_COUNT

def apply_ray_action(
    g,
    v_idx: int,
    dir_idx: int,
    *,
    clone_graph,
    mirrored_dir_idx,
    diagonal_symmetry_ok,
    enforce_symmetry: bool = True,
    stats: Optional[Dict[str, int]] = None,
    ):
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


def run_open_sink_transaction(
    g,
    fronts_init,
    *,
    incident_dir_indices,
    admissible_dirs_for_vertex,
    symmetric_candidate_dirs,
    kawasaki_residual_from_dirs,
    find_vertex_idx,
    on_diag_vertex,
    is_boundary_vertex,
    reflected_dir_idx,
    diagonal_symmetry_ok,
    enforce_symmetry: bool = True,
    max_bounces: int = 14,
    stats: Optional[Dict[str, int]] = None,
):
    if not fronts_init:
        return None
    h = g
    ray_vs = [v for v, _ in fronts_init]
    ray_ds = [d for _, d in fronts_init]
    ray_done = [False] * len(fronts_init)
    config_seen = set()

    def _dir_gap(a: int, b: int) -> int:
        d = abs(a - b) % ANGLE_COUNT
        return min(d, ANGLE_COUNT - d)

    def _next_dir_at_existing_vertex(v_idx: int, incoming_d: int):
        used = set(incident_dir_indices(h, v_idx))
        admissible = admissible_dirs_for_vertex(h, v_idx, enforce_symmetry=False)
        cand = symmetric_candidate_dirs(used, admissible, incoming_d=incoming_d)
        if not cand:
            return None
        scored = []
        for d in cand:
            local = sorted(set(used | {d}))
            ke = kawasaki_residual_from_dirs(local)
            sat = 0 if ke <= 1e-8 else 1
            scored.append((sat, ke, _dir_gap(d, incoming_d), d))
        scored.sort()
        return scored[0][3]

    def _config():
        cur = []
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
            if h.shoot_ray_and_split(cur_v, cur_d, known_hit=hit, stats=stats) is None:
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

            if on_diag_vertex(h, next_v):
                ray_done[rid] = True
                continue
            if is_boundary_vertex(h, next_v):
                ray_done[rid] = True
                continue

            if hit_interior:
                ray_ds[rid] = reflected_dir_idx(cur_d, a_f, b_f)
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
    g,
    v_idx: int,
    dir_idx: int,
    *,
    clone_graph,
    mirrored_dir_idx,
    run_open_sink_transaction,
    repair_open_sink_vertices,
    diagonal_symmetry_ok,
    enforce_symmetry: bool = True,
    max_bounces: int = 14,
    enable_repair: bool = True,
    in_place: bool = False,
    stats: Optional[Dict[str, int]] = None,
):
    h0 = g if in_place else clone_graph(g)
    fronts = [(v_idx, dir_idx)]
    if enforce_symmetry:
        mv = h0.mirror_vertex_idx(v_idx)
        if mv is None:
            return None
        fronts.append((mv, mirrored_dir_idx(dir_idx)))
    uniq = []
    seen = set()
    for f in fronts:
        if f in seen:
            continue
        seen.add(f)
        uniq.append(f)
    out = run_open_sink_transaction(
        h0,
        fronts_init=uniq,
        enforce_symmetry=enforce_symmetry,
        max_bounces=max_bounces,
        stats=stats,
    )
    if out is None:
        return None
    if enable_repair:
        out = repair_open_sink_vertices(
            g,
            out,
            enforce_symmetry=enforce_symmetry,
            max_bounces=max_bounces,
        )
        if enforce_symmetry and not diagonal_symmetry_ok(out):
            return None
    return out


def repair_open_sink_vertices(
    base,
    g,
    *,
    kawasaki_target_vertex_ids,
    vertex_kawasaki_error,
    incident_dir_indices,
    admissible_dirs_for_vertex,
    symmetric_candidate_dirs,
    kawasaki_residual_from_dirs,
    apply_open_sink_action,
    enforce_symmetry: bool,
    max_bounces: int,
    tol: float = 1e-8,
    max_rounds: int = 2,
    max_try_dirs: int = 6,
):
    h = g
    for _ in range(max_rounds):
        targets = [v for v in kawasaki_target_vertex_ids(h) if vertex_kawasaki_error(h, v) > tol]
        if not targets:
            return h
        progressed = False
        for v in targets:
            before_ke = vertex_kawasaki_error(h, v)
            before_total = sum(vertex_kawasaki_error(h, u) for u in kawasaki_target_vertex_ids(h))
            used = set(incident_dir_indices(h, v))
            admissible = admissible_dirs_for_vertex(h, v, enforce_symmetry=enforce_symmetry)
            cand = symmetric_candidate_dirs(used, admissible, incoming_d=None)
            if not cand:
                continue
            cand = sorted(
                cand,
                key=lambda d: kawasaki_residual_from_dirs(sorted(set(used | {d}))),
            )[: max(1, max_try_dirs)]
            best_h = None
            best_key = None
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
                after_total = sum(vertex_kawasaki_error(hh, u) for u in kawasaki_target_vertex_ids(hh))
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


def repair_priority_corners_open_sink(
    g,
    corner_ids,
    *,
    is_boundary_vertex,
    vertex_kawasaki_error,
    incident_dir_indices,
    admissible_dirs_for_vertex,
    kawasaki_residual_from_dirs,
    apply_open_sink_action,
    enforce_symmetry: bool,
    max_bounces: int,
    tol: float = 1e-8,
    max_rounds: int = 2,
    max_try_dirs: int = 6,
):
    h = g
    cset = [v for v in corner_ids if v in h.active_vertices and (not is_boundary_vertex(h, v))]
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
            used = set(incident_dir_indices(h, v))
            admissible = admissible_dirs_for_vertex(h, v, enforce_symmetry=enforce_symmetry)
            cand = [d for d in admissible if d not in used]
            if not cand:
                continue
            cand = sorted(
                cand,
                key=lambda d: kawasaki_residual_from_dirs(sorted(set(used | {d}))),
            )[:max_try_dirs]
            best_h = None
            best_key = None
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


def deactivate_isolated_noncorner_vertices(g, corner_ids) -> None:
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

def run_delete_group_transaction(
    g,
    delete_group,
    corner_ids,
    *,
    kawasaki_score,
    local_kawasaki_metric,
    clone_graph,
    deactivate_isolated_noncorner_vertices,
    diagonal_symmetry_ok,
    enforce_symmetry: bool,
    kawasaki_tol: float,
    baseline_k_bad=None,
):
    if not delete_group:
        return None
    norm_group = {g._norm_edge(a, b) for a, b in delete_group}
    if any(e not in g.edges for e in norm_group):
        return None
    if any(e in g.boundary_edges for e in norm_group):
        return None

    base_bad = baseline_k_bad if baseline_k_bad is not None else kawasaki_score(g, tol=kawasaki_tol)[0]
    touched = set()
    for a, b in norm_group:
        touched.add(a)
        touched.add(b)
    before_bad, before_sum = local_kawasaki_metric(g, touched, kawasaki_tol)

    trial = clone_graph(g)
    for a, b in sorted(norm_group):
        if trial._norm_edge(a, b) not in trial.edges:
            return None
        trial.remove_edge(a, b)
    deactivate_isolated_noncorner_vertices(trial, corner_ids=corner_ids)
    if enforce_symmetry and not diagonal_symmetry_ok(trial):
        return None

    after_bad, after_sum = local_kawasaki_metric(trial, touched, kawasaki_tol)
    if after_bad > before_bad:
        return None
    if after_sum > before_sum + 1e-12:
        return None
    if kawasaki_score(trial, tol=kawasaki_tol)[0] > base_bad:
        return None
    return (trial, len(norm_group))
