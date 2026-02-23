from __future__ import annotations

from math import gcd
from typing import List, Sequence, Tuple

from creasegen.core_types import (
    INV_SQRT2,
    ONE,
    ZERO,
    PointE,
    Qsqrt2,
    _is_power_of_two,
    _q2_cmp,
    _q2_reduce,
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


def _mirror_point_y_eq_x(p: PointE) -> PointE:
    return PointE(x=p.y, y=p.x)


def _parse_dyadic_coeff(tok: str) -> Tuple[int, int]:
    t = tok.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("empty dyadic coefficient")
    sign = 1
    if t.startswith("-"):
        sign = -1
        t = t[1:]
    elif t.startswith("+"):
        t = t[1:]
    if not t:
        raise ValueError("invalid dyadic coefficient")
    if "." in t:
        ip, fp = t.split(".", 1)
        if not ip:
            ip = "0"
        if not fp or (not ip.isdigit()) or (not fp.isdigit()):
            raise ValueError(f"invalid decimal coefficient: {tok}")
        den = 10 ** len(fp)
        num = int(ip) * den + int(fp)
    elif "/" in t:
        xs = t.split("/")
        if len(xs) != 2 or (not xs[0]) or (not xs[1]):
            raise ValueError(f"invalid rational coefficient: {tok}")
        num = int(xs[0])
        den = int(xs[1])
        if den == 0:
            raise ValueError("division by zero in coefficient")
        if den < 0:
            den = -den
            num = -num
    else:
        if not t.isdigit():
            raise ValueError(f"invalid integer coefficient: {tok}")
        return _q2_reduce(sign * int(t), 0, 0)[0], 0

    num *= sign
    if den < 0:
        den = -den
        num = -num
    g = gcd(abs(num), den)
    num //= g
    den //= g
    if not _is_power_of_two(den):
        raise ValueError(f"non-dyadic coefficient is not supported: {tok}")
    k = den.bit_length() - 1
    a, _, k = _q2_reduce(num, 0, k)
    return (a, k)


def _parse_qsqrt2_token(tok: str) -> Qsqrt2:
    t = tok.strip().lower().replace(" ", "")
    if not t:
        raise ValueError("empty token")
    if t in ("sqrt2", "sqrt(2)"):
        return Qsqrt2(0, 1, 0)
    if t in ("1/sqrt2", "1/sqrt(2)", "sqrt2/2", "sqrt(2)/2"):
        return INV_SQRT2
    if "sqrt2" in t or "sqrt(2)" in t:
        t = t.replace("sqrt(2)", "sqrt2")
        sign = 1
        if t.startswith("-"):
            sign = -1
            t = t[1:]
        if t == "sqrt2":
            return Qsqrt2(0, sign, 0)
        if t.endswith("*sqrt2"):
            num, k = _parse_dyadic_coeff(t[:-6])
            return Qsqrt2(0, sign * num, k)
        if t.startswith("sqrt2/"):
            num, k = _parse_dyadic_coeff("1/" + t.split("/")[1])
            return Qsqrt2(0, sign * num, k)
        raise ValueError(f"unsupported sqrt2 token: {tok}")
    num, k = _parse_dyadic_coeff(t)
    return Qsqrt2(num, 0, k)


def parse_corners(text: str) -> List[PointE]:
    pts: List[PointE] = []
    chunks = [c.strip() for c in text.split(";") if c.strip()]
    if not chunks:
        raise ValueError("corners is empty")
    for c in chunks:
        c = c.strip()
        if c.startswith("(") and c.endswith(")"):
            c = c[1:-1].strip()
        xy = [x.strip() for x in c.split(",")]
        if len(xy) != 2:
            raise ValueError(f"invalid corner format: {c}")
        p = PointE(_parse_qsqrt2_token(xy[0]), _parse_qsqrt2_token(xy[1]))
        if not _in_square(p):
            raise ValueError(f"corner out of [0,1]^2: {c}")
        pts.append(p)
    return pts


def corners_diag_symmetric(corners: Sequence[PointE]) -> bool:
    s = {_point_key(p) for p in corners}
    for p in corners:
        if _point_key(_mirror_point_y_eq_x(p)) not in s:
            return False
    return True

