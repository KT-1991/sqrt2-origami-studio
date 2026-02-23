from __future__ import annotations

from functools import lru_cache
from math import atan2, pi
from typing import List, Optional, Sequence, Set, Tuple

from creasegen.core_types import ANGLE_COUNT, DIRS_F, DIRS_UNIT_F
from creasegen.scoring import _norm_angle


def _cross_f(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


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


def _dir_gap_steps(a: int, b: int) -> int:
    d = abs(a - b) % ANGLE_COUNT
    return min(d, ANGLE_COUNT - d)

