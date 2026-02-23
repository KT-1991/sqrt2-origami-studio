from __future__ import annotations


def _is_boundary_vertex(g, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    return abs(x) <= tol or abs(x - 1.0) <= tol or abs(y) <= tol or abs(y - 1.0) <= tol


def _is_square_corner_vertex(g, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    on_x = abs(x) <= tol or abs(x - 1.0) <= tol
    on_y = abs(y) <= tol or abs(y - 1.0) <= tol
    return on_x and on_y


def _on_diag_vertex(g, v_idx: int, tol: float = 1e-10) -> bool:
    x, y = g.points_f[v_idx]
    return abs(x - y) <= tol


def diagonal_symmetry_ok(g) -> bool:
    for i, j in g.edges:
        mi = g.mirror_vertex_idx(i)
        mj = g.mirror_vertex_idx(j)
        if mi is None or mj is None:
            return False
        e = (mi, mj) if mi < mj else (mj, mi)
        if e not in g.edges:
            return False
    return True

