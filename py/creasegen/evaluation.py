from __future__ import annotations

from typing import List, Sequence, Set, Tuple


def kawasaki_score(
    g,
    *,
    kawasaki_target_vertex_ids,
    vertex_kawasaki_error,
    tol: float = 1e-8,
) -> Tuple[int, float, int]:
    targets = kawasaki_target_vertex_ids(g)
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
    g,
    corner_ids: Sequence[int],
    max_deg: float,
    *,
    corner_score_fn,
    kawasaki_score_fn,
    min_corner_lines: int = 2,
    kawasaki_tol: float = 1e-8,
) -> Tuple[int, int, int, float, float, float]:
    bad_corner, lowdeg, total_corner, lowdeg_pen = corner_score_fn(
        g,
        corner_ids=corner_ids,
        max_deg=max_deg,
        min_corner_lines=min_corner_lines,
    )
    bad_k, total_k, _ = kawasaki_score_fn(g, tol=kawasaki_tol)
    # Prioritize global Kawasaki satisfaction first, then corner metrics.
    return (bad_k, bad_corner, lowdeg, total_k, total_corner, lowdeg_pen)


def preserve_satisfied_corners(
    before_g,
    after_g,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int,
    *,
    corner_condition_error,
    corner_line_count,
    tol: float = 1e-12,
) -> bool:
    for v in corner_ids:
        if v not in before_g.active_vertices or v not in after_g.active_vertices:
            continue
        before_ok = (
            corner_condition_error(before_g, v, max_deg=max_deg) <= tol
            and corner_line_count(before_g, v) >= min_corner_lines
        )
        if not before_ok:
            continue
        if corner_condition_error(after_g, v, max_deg=max_deg) > tol:
            return False
        if corner_line_count(after_g, v) < min_corner_lines:
            return False
    return True


def priority_corner_kawasaki_score(
    g,
    corner_ids: Sequence[int],
    *,
    is_boundary_vertex,
    vertex_kawasaki_error,
    tol: float = 1e-8,
) -> Tuple[int, float]:
    bad = 0
    total = 0.0
    for v in corner_ids:
        if v not in g.active_vertices:
            continue
        if is_boundary_vertex(g, v):
            continue
        ke = vertex_kawasaki_error(g, v)
        val = 1000.0 if ke == float("inf") else ke
        total += val
        if val > tol:
            bad += 1
    return (bad, total)


def violating_vertex_priority(
    g,
    corner_ids: Sequence[int],
    max_deg: float,
    min_corner_lines: int,
    kawasaki_tol: float,
    *,
    corner_condition_error,
    corner_line_count,
    kawasaki_target_vertex_ids,
    vertex_kawasaki_error,
    is_boundary_vertex,
) -> List[int]:
    cset = set(corner_ids)
    cand: Set[int] = set()
    for v in corner_ids:
        if corner_condition_error(g, v, max_deg=max_deg) > 1e-12:
            cand.add(v)
        if corner_line_count(g, v) < min_corner_lines:
            cand.add(v)
    for v in kawasaki_target_vertex_ids(g):
        if vertex_kawasaki_error(g, v) > kawasaki_tol:
            cand.add(v)

    interior_corners = [v for v in corner_ids if not is_boundary_vertex(g, v)]
    interior_corners_all_satisfied = all(
        corner_condition_error(g, v, max_deg=max_deg) <= 1e-12
        and corner_line_count(g, v) >= min_corner_lines
        for v in interior_corners
    )

    def _priority_group(v: int) -> int:
        is_corner = v in cset
        is_boundary_corner = is_corner and is_boundary_vertex(g, v)
        if interior_corners_all_satisfied:
            if is_boundary_corner:
                return 0
            return 1 if not is_corner else 2
        return 0 if not is_corner else 1

    return sorted(
        list(cand),
        key=lambda v: (
            _priority_group(v),
            1 if is_boundary_vertex(g, v) else 0,
            -vertex_kawasaki_error(g, v),
            -corner_condition_error(g, v, max_deg=max_deg),
            -(max(0, min_corner_lines - corner_line_count(g, v))),
        ),
    )
