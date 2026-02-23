from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import gcd
from typing import List, Optional, Tuple


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _q2_reduce(a: int, b: int, k: int) -> Tuple[int, int, int]:
    if a == 0 and b == 0:
        return (0, 0, 0)
    while k > 0 and (a & 1) == 0 and (b & 1) == 0:
        a >>= 1
        b >>= 1
        k -= 1
    return (a, b, k)


def _ceil_div_pow2(n: int, k: int) -> int:
    if n <= 0:
        return 0
    if k <= 0:
        return n
    step = 1 << k
    return (n + step - 1) // step


@dataclass(frozen=True)
class Qsqrt2:
    # Represents (a + b*sqrt(2)) / 2^k with integer a,b.
    a: int
    b: int
    k: int = 0

    def __post_init__(self) -> None:
        if self.k < 0:
            raise ValueError("k must be >= 0")
        a, b, k = _q2_reduce(self.a, self.b, self.k)
        object.__setattr__(self, "a", a)
        object.__setattr__(self, "b", b)
        object.__setattr__(self, "k", k)

    @staticmethod
    def from_int(n: int) -> "Qsqrt2":
        return Qsqrt2(n, 0, 0)

    @staticmethod
    def from_dyadic(num: int, k: int) -> "Qsqrt2":
        return Qsqrt2(num, 0, k)

    @staticmethod
    def from_ratio(num: int, den: int) -> "Qsqrt2":
        if den <= 0:
            raise ValueError("denominator must be positive")
        if not _is_power_of_two(den):
            raise ValueError("non-dyadic rational is not supported")
        return Qsqrt2(num, 0, den.bit_length() - 1)

    def __add__(self, o: "Qsqrt2") -> "Qsqrt2":
        k = max(self.k, o.k)
        a = (self.a << (k - self.k)) + (o.a << (k - o.k))
        b = (self.b << (k - self.k)) + (o.b << (k - o.k))
        return Qsqrt2(a, b, k)

    def __sub__(self, o: "Qsqrt2") -> "Qsqrt2":
        k = max(self.k, o.k)
        a = (self.a << (k - self.k)) - (o.a << (k - o.k))
        b = (self.b << (k - self.k)) - (o.b << (k - o.k))
        return Qsqrt2(a, b, k)

    def __mul__(self, o: "Qsqrt2") -> "Qsqrt2":
        return Qsqrt2(
            self.a * o.a + 2 * self.b * o.b,
            self.a * o.b + self.b * o.a,
            self.k + o.k,
        )

    def __neg__(self) -> "Qsqrt2":
        return Qsqrt2(-self.a, -self.b, self.k)

    def __truediv__(self, o: "Qsqrt2") -> "Qsqrt2":
        return _q2_div_int_to_q2(_q2_to_int(self), _q2_to_int(o))

    def approx(self) -> float:
        scale = 2.0 ** (-self.k)
        return (float(self.a) + float(self.b) * (2.0**0.5)) * scale


@dataclass(frozen=True)
class Q2Int:
    # Represents (a + b*sqrt(2)) / 2^k with integer a,b.
    a: int
    b: int
    k: int


ZERO = Qsqrt2.from_int(0)
ONE = Qsqrt2.from_int(1)
HALF = Qsqrt2.from_dyadic(1, 1)
INV_SQRT2 = Qsqrt2(0, 1, 1)
SQRT2_MINUS_ONE = Qsqrt2(-1, 1, 0)
ZERO_I = Q2Int(0, 0, 0)


@dataclass(frozen=True)
class PointE:
    x: Qsqrt2
    y: Qsqrt2

    def approx(self) -> Tuple[float, float]:
        return (self.x.approx(), self.y.approx())


ANGLE_COUNT = 16
FACE_INDEX_BUILD_THRESHOLD = 8
_S = SQRT2_MINUS_ONE
DIRS: List[Tuple[Qsqrt2, Qsqrt2]] = [
    (ONE, ZERO),
    (ONE, _S),
    (ONE, ONE),
    (_S, ONE),
    (ZERO, ONE),
    (-_S, ONE),
    (-ONE, ONE),
    (-ONE, _S),
    (-ONE, ZERO),
    (-ONE, -_S),
    (-ONE, -ONE),
    (-_S, -ONE),
    (ZERO, -ONE),
    (_S, -ONE),
    (ONE, -ONE),
    (ONE, -_S),
]
DIRS_F: List[Tuple[float, float]] = [(dx.approx(), dy.approx()) for dx, dy in DIRS]
DIRS_UNIT_F: List[Tuple[float, float]] = []
for _rx, _ry in DIRS_F:
    _rn = (_rx * _rx + _ry * _ry) ** 0.5
    if _rn <= 1e-15:
        DIRS_UNIT_F.append((0.0, 0.0))
    else:
        DIRS_UNIT_F.append((_rx / _rn, _ry / _rn))


@lru_cache(maxsize=1 << 15)
def _q2_to_int(z: Qsqrt2) -> Optional[Q2Int]:
    return Q2Int(a=z.a, b=z.b, k=z.k)


DIRS_I: List[Tuple[Q2Int, Q2Int]] = []
for _dx, _dy in DIRS:
    _dxi = _q2_to_int(_dx)
    _dyi = _q2_to_int(_dy)
    if _dxi is None or _dyi is None:
        raise ValueError("direction set must be dyadic")
    DIRS_I.append((_dxi, _dyi))


def _q2_sign_aligned(a: int, b: int) -> int:
    if a == 0 and b == 0:
        return 0
    if b == 0:
        return 1 if a > 0 else -1
    if a == 0:
        return 1 if b > 0 else -1
    sa = 1 if a > 0 else -1
    sb = 1 if b > 0 else -1
    if sa == sb:
        return sa
    aa = a * a
    bb2 = 2 * b * b
    if sa > 0 and sb < 0:
        return 1 if aa > bb2 else -1
    return 1 if bb2 > aa else -1


def _q2_sign(z: Qsqrt2) -> int:
    return _q2_sign_aligned(z.a, z.b)


def _q2_cmp(x: Qsqrt2, y: Qsqrt2) -> int:
    k = max(x.k, y.k)
    ax = x.a << (k - x.k)
    bx = x.b << (k - x.k)
    ay = y.a << (k - y.k)
    by = y.b << (k - y.k)
    return _q2_sign_aligned(ax - ay, bx - by)


def _q2_cmp_int(x: Q2Int, y: Q2Int) -> int:
    k = max(x.k, y.k)
    ax = x.a << (k - x.k)
    bx = x.b << (k - x.k)
    ay = y.a << (k - y.k)
    by = y.b << (k - y.k)
    return _q2_sign_aligned(ax - ay, bx - by)


def _q2_sub_int(x: Q2Int, y: Q2Int) -> Q2Int:
    k = max(x.k, y.k)
    ax = x.a << (k - x.k)
    bx = x.b << (k - x.k)
    ay = y.a << (k - y.k)
    by = y.b << (k - y.k)
    return Q2Int(a=ax - ay, b=bx - by, k=k)


def _q2_neg_int(x: Q2Int) -> Q2Int:
    return Q2Int(a=-x.a, b=-x.b, k=x.k)


def _q2_mul_int(x: Q2Int, y: Q2Int) -> Q2Int:
    return Q2Int(
        a=x.a * y.a + 2 * x.b * y.b,
        b=x.a * y.b + x.b * y.a,
        k=x.k + y.k,
    )


def _q2_cross_int(ax: Q2Int, ay: Q2Int, bx: Q2Int, by: Q2Int) -> Q2Int:
    return _q2_sub_int(_q2_mul_int(ax, by), _q2_mul_int(ay, bx))


def _q2_div_int_to_q2(x: Q2Int, y: Q2Int) -> Qsqrt2:
    den = y.a * y.a - 2 * y.b * y.b
    if den == 0:
        raise ZeroDivisionError("singular Qsqrt2 inverse")
    na = x.a * y.a - 2 * x.b * y.b
    nb = -x.a * y.b + x.b * y.a
    if den < 0:
        den = -den
        na = -na
        nb = -nb
    g = gcd(gcd(abs(na), abs(nb)), den)
    if g > 1:
        na //= g
        nb //= g
        den //= g
    if not _is_power_of_two(den):
        raise ValueError("non-dyadic division result")
    den_k = den.bit_length() - 1
    dk = x.k - y.k
    if dk >= 0:
        return Qsqrt2(na, nb, den_k + dk)
    scale = -dk
    return Qsqrt2(na << scale, nb << scale, den_k)

