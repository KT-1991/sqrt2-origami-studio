from __future__ import annotations

from typing import Dict, Optional, Tuple

from creasegen.core_types import (
    ANGLE_COUNT,
    ONE,
    ZERO,
    PointE,
    Qsqrt2,
    _ceil_div_pow2,
    _q2_cmp,
)


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


def _required_norm_bounds_for_point(p: PointE) -> Optional[Tuple[int, int]]:
    bx = _required_bounds_for_qsqrt2(p.x)
    by = _required_bounds_for_qsqrt2(p.y)
    if bx is None or by is None:
        return None
    ax = _ceil_div_pow2(bx[1], bx[0])
    bxn = _ceil_div_pow2(bx[2], bx[0])
    ay = _ceil_div_pow2(by[1], by[0])
    byn = _ceil_div_pow2(by[2], by[0])
    return (max(ax, ay), max(bxn, byn))


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
    req_norm = _required_norm_bounds_for_point(p)
    if req_norm is not None:
        ran, rbn = req_norm
        stats["expand_need_a_norm"] = max(stats.get("expand_need_a_norm", 0), ran)
        stats["expand_need_b_norm"] = max(stats.get("expand_need_b_norm", 0), rbn)


def mirror_point_y_eq_x(p: PointE) -> PointE:
    return PointE(p.y, p.x)


def mirrored_dir_idx(dir_idx: int) -> int:
    return (4 - dir_idx) % ANGLE_COUNT

