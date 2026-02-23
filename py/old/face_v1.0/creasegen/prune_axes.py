from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

from creasegen.core_types import ANGLE_COUNT, DIRS, DIRS_UNIT_F
from creasegen.direction import _cross_f


def line_key_eq(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    return a[0] == b[0] and a[1] == b[1] and a[2] == b[2] and a[3] == b[3]


def edge_line_key(
    g,
    e: Tuple[int, int],
    *,
    edge_dir_from,
    cross,
) -> Optional[Tuple[int, int, int, int]]:
    a, b = g._norm_edge(e[0], e[1])
    d = g.edge_dir_idx.get((a, b))
    if d is None:
        d = edge_dir_from(g, a, b)
    if d is None:
        return None
    axis_d = d % (ANGLE_COUNT // 2)
    p = g.points[a]
    rx, ry = DIRS[axis_d]
    c = cross(p.x, p.y, rx, ry)
    return (axis_d, c.a, c.b, c.k)


def edge_center_dist2(g, e: Tuple[int, int]) -> float:
    i, j = g._norm_edge(e[0], e[1])
    x1, y1 = g.points_f[i]
    x2, y2 = g.points_f[j]
    cx = 0.5 * (x1 + x2)
    cy = 0.5 * (y1 + y2)
    return (cx - 0.5) ** 2 + (cy - 0.5) ** 2


def _build_active_vertex_lookup(
    g,
    scale: int = 10_000_000,
) -> Dict[Tuple[int, int], List[int]]:
    out: Dict[Tuple[int, int], List[int]] = {}
    for v in g.active_vertices:
        x, y = g.points_f[v]
        key = (int(round(x * scale)), int(round(y * scale)))
        out.setdefault(key, []).append(v)
    return out


def _lookup_active_vertex_by_xy(
    g,
    lookup: Dict[Tuple[int, int], List[int]],
    x: float,
    y: float,
    scale: int = 10_000_000,
    tol: float = 2e-6,
) -> Optional[int]:
    kx = int(round(x * scale))
    ky = int(round(y * scale))
    best_v: Optional[int] = None
    best_d2: Optional[float] = None
    tol2 = tol * tol
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            vs = lookup.get((kx + dx, ky + dy))
            if not vs:
                continue
            for v in vs:
                vx, vy = g.points_f[v]
                d2 = (vx - x) * (vx - x) + (vy - y) * (vy - y)
                if d2 > tol2:
                    continue
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    best_v = v
    return best_v


def _mirror_xy_across_axis(
    x: float,
    y: float,
    ax: float,
    ay: float,
    tx: float,
    ty: float,
) -> Tuple[float, float]:
    vx = x - ax
    vy = y - ay
    proj = vx * tx + vy * ty
    fx = ax + proj * tx
    fy = ay + proj * ty
    return (2.0 * fx - x, 2.0 * fy - y)


def _signed_dist_to_axis(
    x: float,
    y: float,
    ax: float,
    ay: float,
    tx: float,
    ty: float,
) -> float:
    # Signed distance up to scale by |t| (t is unit in current usage).
    return _cross_f(tx, ty, x - ax, y - ay)


def _edge_is_deletable(g, u: int, v: int) -> bool:
    e = g._norm_edge(u, v)
    return e in g.edges and e not in g.boundary_edges


def best_axis_cycle_group_for_line(
    g,
    line_key: Tuple[int, int, int, int],
    group_edges: Sequence[Tuple[int, int]],
    max_pairs: int = 12,
) -> Optional[Tuple[int, Set[Tuple[int, int]], Tuple[int, int]]]:
    if not group_edges:
        return None
    axis_d = line_key[0]
    tx, ty = DIRS_UNIT_F[axis_d]
    if abs(tx) + abs(ty) <= 1e-15:
        return None

    axis_vertices = sorted({v for e in group_edges for v in e if v in g.active_vertices})
    if len(axis_vertices) < 2:
        return None

    # Anchor point on axis.
    a0x, a0y = g.points_f[group_edges[0][0]]
    lookup = _build_active_vertex_lookup(g)

    # Candidate endpoint pairs on axis (favor longer spans).
    proj_vs: List[Tuple[float, int]] = []
    for v in axis_vertices:
        x, y = g.points_f[v]
        proj_vs.append((x * tx + y * ty, v))
    proj_vs.sort()
    pair_keys: List[Tuple[float, int, int]] = []
    n = len(proj_vs)
    for i in range(n):
        for j in range(i + 1, n):
            span = proj_vs[j][0] - proj_vs[i][0]
            if span <= 1e-8:
                continue
            pair_keys.append((-span, i, j))
    pair_keys.sort()
    if len(pair_keys) > max_pairs:
        pair_keys = pair_keys[:max_pairs]

    best: Optional[Tuple[int, int, Set[Tuple[int, int]], Tuple[int, int]]] = None

    def _try_update(cycle_len: int, group: Set[Tuple[int, int]], rep_edge: Tuple[int, int], tie: int) -> None:
        nonlocal best
        key = (cycle_len, tie)
        if best is None or key < (best[0], best[1]):
            best = (cycle_len, tie, group, rep_edge)

    for _, i, j in pair_keys:
        a = proj_vs[i][1]
        c = proj_vs[j][1]
        if a == c:
            continue
        # Enumerate one-side paths A->...->C (positive signed side only), mirror to opposite side.
        # Length-2 path gives 4-edge cycle; length-3 path gives 6-edge cycle.
        for b in g.adj.get(a, set()):
            if b == c:
                continue
            if not _edge_is_deletable(g, a, b):
                continue
            bx, by = g.points_f[b]
            sb = _signed_dist_to_axis(bx, by, a0x, a0y, tx, ty)
            if sb <= 1e-8:
                continue
            bmx, bmy = _mirror_xy_across_axis(bx, by, a0x, a0y, tx, ty)
            bm = _lookup_active_vertex_by_xy(g, lookup, bmx, bmy)
            if bm is None or bm == b:
                continue
            if not _edge_is_deletable(g, a, bm):
                continue

            # 4-cycle candidate: A-B-C and mirrored A-Bm-C.
            if _edge_is_deletable(g, b, c) and _edge_is_deletable(g, bm, c):
                group4 = {
                    g._norm_edge(a, b),
                    g._norm_edge(b, c),
                    g._norm_edge(a, bm),
                    g._norm_edge(bm, c),
                }
                _try_update(4, group4, g._norm_edge(a, c), tie=0)

            # 6-cycle candidate: A-B-E-C and mirrored A-Bm-Em-C.
            for e in g.adj.get(b, set()):
                if e == a or e == b or e == c:
                    continue
                if not _edge_is_deletable(g, b, e):
                    continue
                if not _edge_is_deletable(g, e, c):
                    continue
                ex, ey = g.points_f[e]
                se = _signed_dist_to_axis(ex, ey, a0x, a0y, tx, ty)
                if se <= 1e-8:
                    continue
                emx, emy = _mirror_xy_across_axis(ex, ey, a0x, a0y, tx, ty)
                em = _lookup_active_vertex_by_xy(g, lookup, emx, emy)
                if em is None or em == e or em == b or em == c:
                    continue
                if not _edge_is_deletable(g, bm, em):
                    continue
                if not _edge_is_deletable(g, em, c):
                    continue
                group6 = {
                    g._norm_edge(a, b),
                    g._norm_edge(b, e),
                    g._norm_edge(e, c),
                    g._norm_edge(a, bm),
                    g._norm_edge(bm, em),
                    g._norm_edge(em, c),
                }
                _try_update(6, group6, g._norm_edge(a, c), tie=1)

    if best is None:
        return None
    return (best[0], best[2], best[3])


def collect_prune_axis_representatives(
    g,
    max_candidates: int,
    *,
    edge_line_key_fn,
    edge_center_dist2_fn,
    best_axis_cycle_group_for_line_fn,
) -> List[Tuple[Tuple[int, int], int]]:
    candidates = [e for e in g.edges if e not in g.boundary_edges]
    line_groups: Dict[Tuple[int, int, int, int], List[Tuple[int, int]]] = {}
    line_rank: Dict[Tuple[int, int, int, int], Tuple[float, int]] = {}
    for e in candidates:
        lk = edge_line_key_fn(g, e)
        if lk is None:
            continue
        line_groups.setdefault(lk, []).append(e)
        rk = (edge_center_dist2_fn(g, e), -g.edge_birth.get(e, -1))
        prv = line_rank.get(lk)
        if prv is None or rk < prv:
            line_rank[lk] = rk

    ordered_lines = sorted(line_groups.keys(), key=lambda k: line_rank[k])
    line_scan_limit = max(max_candidates * 6, max_candidates)
    targeted: List[Tuple[Tuple[int, int], int]] = []
    for lk in ordered_lines[:line_scan_limit]:
        best = best_axis_cycle_group_for_line_fn(g, lk, line_groups.get(lk, []))
        if best is None:
            continue
        best_len, _, rep_edge = best
        targeted.append((rep_edge, best_len))
        if len(targeted) >= max_candidates:
            break

    targeted.sort(
        key=lambda it: (
            0 if it[1] == 4 else 1,
            edge_center_dist2_fn(g, it[0]),
            -g.edge_birth.get(it[0], -1),
        )
    )
    return targeted


def collect_axis_cycle_targets(
    g,
    max_candidates: int,
    *,
    edge_line_key_fn,
    edge_center_dist2_fn,
    best_axis_cycle_group_for_line_fn,
) -> List[Tuple[Tuple[int, int, int, int], Tuple[int, int], int, Set[Tuple[int, int]]]]:
    candidates = [e for e in g.edges if e not in g.boundary_edges]
    line_groups: Dict[Tuple[int, int, int, int], List[Tuple[int, int]]] = {}
    line_rank: Dict[Tuple[int, int, int, int], Tuple[float, int]] = {}
    for e in candidates:
        lk = edge_line_key_fn(g, e)
        if lk is None:
            continue
        line_groups.setdefault(lk, []).append(e)
        rk = (edge_center_dist2_fn(g, e), -g.edge_birth.get(e, -1))
        prv = line_rank.get(lk)
        if prv is None or rk < prv:
            line_rank[lk] = rk

    ordered_lines = sorted(line_groups.keys(), key=lambda k: line_rank[k])
    line_scan_limit = max(max_candidates * 6, max_candidates)
    out: List[Tuple[Tuple[int, int, int, int], Tuple[int, int], int, Set[Tuple[int, int]]]] = []
    for lk in ordered_lines[:line_scan_limit]:
        best = best_axis_cycle_group_for_line_fn(g, lk, line_groups.get(lk, []))
        if best is None:
            continue
        cycle_len, group, rep_edge = best
        out.append((lk, rep_edge, cycle_len, group))
        if len(out) >= max_candidates:
            break
    out.sort(
        key=lambda it: (
            0 if it[2] == 4 else 1,
            edge_center_dist2_fn(g, it[1]),
            -g.edge_birth.get(it[1], -1),
        )
    )
    return out


def refresh_graph_by_pruning(
    g,
    corner_ids,
    *,
    clone_graph,
    global_score,
    priority_corner_kawasaki_score,
    edge_line_key_fn,
    collect_axis_cycle_targets_fn,
    line_key_eq_fn,
    run_delete_group_transaction_fn,
    max_deg: float,
    min_corner_lines: int,
    kawasaki_tol: float,
    enforce_symmetry: bool = True,
    max_candidates: int = 24,
    delete_max_steps: int = 8,
    stats: Optional[Dict[str, int]] = None,
    probe_line_key: Optional[Tuple[int, int, int, int]] = None,
):
    _ = delete_max_steps
    h = clone_graph(g)
    best_sc = global_score(
        h,
        corner_ids=corner_ids,
        max_deg=max_deg,
        min_corner_lines=min_corner_lines,
        kawasaki_tol=kawasaki_tol,
    )
    best_ck = priority_corner_kawasaki_score(h, corner_ids=corner_ids, tol=kawasaki_tol)

    candidates = [e for e in h.edges if e not in h.boundary_edges]
    line_groups: Dict[Tuple[int, int, int, int], List[Tuple[int, int]]] = {}
    unknown_line_key_total = 0
    for e in candidates:
        lk = edge_line_key_fn(h, e)
        if lk is None:
            unknown_line_key_total += 1
            continue
        line_groups.setdefault(lk, []).append(e)

    if stats is not None:
        stats["prune_unknown_line_key_total"] = stats.get("prune_unknown_line_key_total", 0) + unknown_line_key_total
        stats["prune_line_groups_total"] = stats.get("prune_line_groups_total", 0) + len(line_groups)
        if probe_line_key is not None and probe_line_key in line_groups:
            stats["prune_probe_line_present"] = stats.get("prune_probe_line_present", 0) + 1

    targeted = collect_axis_cycle_targets_fn(h, max_candidates=max_candidates)
    if stats is not None:
        stats["prune_targeted_edges_total"] = stats.get("prune_targeted_edges_total", 0) + len(targeted)
        if probe_line_key is not None and any(line_key_eq_fn(lk, probe_line_key) for lk, _, _, _ in targeted):
            stats["prune_probe_line_targeted"] = stats.get("prune_probe_line_targeted", 0) + 1

    removed_total = 0
    tried_axis: Set[Tuple[int, int, int, int]] = set()
    for lk, rep_edge, _, group in targeted[:max_candidates]:
        _ = rep_edge
        if lk in tried_axis:
            continue
        tried_axis.add(lk)
        is_probe = probe_line_key is not None and line_key_eq_fn(lk, probe_line_key)
        if stats is not None:
            stats["prune_tx_attempted_total"] = stats.get("prune_tx_attempted_total", 0) + 1
            if is_probe:
                stats["prune_probe_line_attempted"] = stats.get("prune_probe_line_attempted", 0) + 1
        tx = run_delete_group_transaction_fn(
            h,
            delete_group=group,
            corner_ids=corner_ids,
            enforce_symmetry=enforce_symmetry,
            kawasaki_tol=kawasaki_tol,
            baseline_k_bad=best_sc[0],
        )
        if tx is None:
            if stats is not None:
                stats["prune_tx_fail_total"] = stats.get("prune_tx_fail_total", 0) + 1
                if is_probe:
                    stats["prune_probe_line_fail_tx"] = stats.get("prune_probe_line_fail_tx", 0) + 1
            continue
        trial, removed = tx
        if removed <= 0:
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
            removed_total += removed
            if stats is not None:
                stats["prune_tx_accepted_total"] = stats.get("prune_tx_accepted_total", 0) + 1
                if is_probe:
                    stats["prune_probe_line_accepted"] = stats.get("prune_probe_line_accepted", 0) + 1
        else:
            if stats is not None:
                stats["prune_tx_reject_score_total"] = stats.get("prune_tx_reject_score_total", 0) + 1
                if is_probe:
                    stats["prune_probe_line_reject_score"] = stats.get("prune_probe_line_reject_score", 0) + 1

    return h, removed_total
