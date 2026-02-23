import type { PointE, Qsqrt2 } from "./types";

export interface Q2Int {
  a: bigint;
  b: bigint;
  k: number;
}

function toBigintInt(n: number | bigint, field: string): bigint {
  if (typeof n === "bigint") {
    return n;
  }
  if (!Number.isInteger(n)) {
    throw new Error(`${field} must be an integer`);
  }
  return BigInt(n);
}

function absBigint(x: bigint): bigint {
  return x < 0n ? -x : x;
}

function gcdBigint(a: bigint, b: bigint): bigint {
  let x = absBigint(a);
  let y = absBigint(b);
  while (y !== 0n) {
    const t = x % y;
    x = y;
    y = t;
  }
  return x;
}

function bitLength(n: bigint): number {
  if (n <= 0n) {
    return 0;
  }
  let x = n;
  let bits = 0;
  while (x > 0n) {
    x >>= 1n;
    bits += 1;
  }
  return bits;
}

export function isPowerOfTwo(n: number): boolean {
  return Number.isInteger(n) && n > 0 && (n & (n - 1)) === 0;
}

function isPowerOfTwoBigint(n: bigint): boolean {
  return n > 0n && (n & (n - 1n)) === 0n;
}

export function q2Reduce(
  aIn: number | bigint,
  bIn: number | bigint,
  kIn: number,
): Qsqrt2 {
  if (!Number.isInteger(kIn) || kIn < 0) {
    throw new Error("k must be a non-negative integer");
  }
  let a = toBigintInt(aIn, "a");
  let b = toBigintInt(bIn, "b");
  let k = kIn;
  if (a === 0n && b === 0n) {
    return { a: 0n, b: 0n, k: 0 };
  }
  while (k > 0 && (a & 1n) === 0n && (b & 1n) === 0n) {
    a >>= 1n;
    b >>= 1n;
    k -= 1;
  }
  return { a, b, k };
}

export function qsqrt2(
  a: number | bigint,
  b: number | bigint,
  k = 0,
): Qsqrt2 {
  return q2Reduce(a, b, k);
}

export function fromInt(n: number | bigint): Qsqrt2 {
  return qsqrt2(n, 0n, 0);
}

export function fromDyadic(num: number | bigint, k: number): Qsqrt2 {
  return qsqrt2(num, 0n, k);
}

export function fromRatio(
  numIn: number | bigint,
  denIn: number | bigint,
): Qsqrt2 {
  const num = toBigintInt(numIn, "num");
  const den = toBigintInt(denIn, "den");
  if (den <= 0n) {
    throw new Error("denominator must be positive");
  }
  const denNum = Number(den);
  if (!Number.isSafeInteger(denNum) || !isPowerOfTwo(denNum)) {
    throw new Error("non-dyadic rational is not supported");
  }
  const k = bitLength(den) - 1;
  return qsqrt2(num, 0n, k);
}

export function add(x: Qsqrt2, y: Qsqrt2): Qsqrt2 {
  const k = Math.max(x.k, y.k);
  const ax = x.a << BigInt(k - x.k);
  const bx = x.b << BigInt(k - x.k);
  const ay = y.a << BigInt(k - y.k);
  const by = y.b << BigInt(k - y.k);
  return qsqrt2(ax + ay, bx + by, k);
}

export function sub(x: Qsqrt2, y: Qsqrt2): Qsqrt2 {
  const k = Math.max(x.k, y.k);
  const ax = x.a << BigInt(k - x.k);
  const bx = x.b << BigInt(k - x.k);
  const ay = y.a << BigInt(k - y.k);
  const by = y.b << BigInt(k - y.k);
  return qsqrt2(ax - ay, bx - by, k);
}

export function mul(x: Qsqrt2, y: Qsqrt2): Qsqrt2 {
  return qsqrt2(
    x.a * y.a + 2n * x.b * y.b,
    x.a * y.b + x.b * y.a,
    x.k + y.k,
  );
}

export function neg(x: Qsqrt2): Qsqrt2 {
  return qsqrt2(-x.a, -x.b, x.k);
}

export function toQ2Int(z: Qsqrt2): Q2Int {
  return { a: z.a, b: z.b, k: z.k };
}

export function q2CmpInt(x: Q2Int, y: Q2Int): number {
  const k = Math.max(x.k, y.k);
  const ax = x.a << BigInt(k - x.k);
  const bx = x.b << BigInt(k - x.k);
  const ay = y.a << BigInt(k - y.k);
  const by = y.b << BigInt(k - y.k);
  return q2SignAligned(ax - ay, bx - by);
}

export function q2SubInt(x: Q2Int, y: Q2Int): Q2Int {
  const k = Math.max(x.k, y.k);
  const ax = x.a << BigInt(k - x.k);
  const bx = x.b << BigInt(k - x.k);
  const ay = y.a << BigInt(k - y.k);
  const by = y.b << BigInt(k - y.k);
  return { a: ax - ay, b: bx - by, k };
}

export function q2NegInt(x: Q2Int): Q2Int {
  return { a: -x.a, b: -x.b, k: x.k };
}

export function q2MulInt(x: Q2Int, y: Q2Int): Q2Int {
  return {
    a: x.a * y.a + 2n * x.b * y.b,
    b: x.a * y.b + x.b * y.a,
    k: x.k + y.k,
  };
}

export function q2CrossInt(ax: Q2Int, ay: Q2Int, bx: Q2Int, by: Q2Int): Q2Int {
  return q2SubInt(q2MulInt(ax, by), q2MulInt(ay, bx));
}

export function q2SignAligned(a: bigint, b: bigint): number {
  if (a === 0n && b === 0n) {
    return 0;
  }
  if (b === 0n) {
    return a > 0n ? 1 : -1;
  }
  if (a === 0n) {
    return b > 0n ? 1 : -1;
  }
  const sa = a > 0n ? 1 : -1;
  const sb = b > 0n ? 1 : -1;
  if (sa === sb) {
    return sa;
  }
  const aa = a * a;
  const bb2 = 2n * b * b;
  if (sa > 0 && sb < 0) {
    return aa > bb2 ? 1 : -1;
  }
  return bb2 > aa ? 1 : -1;
}

export function q2Sign(z: Qsqrt2): number {
  return q2SignAligned(z.a, z.b);
}

export function q2Cmp(x: Qsqrt2, y: Qsqrt2): number {
  const k = Math.max(x.k, y.k);
  const ax = x.a << BigInt(k - x.k);
  const bx = x.b << BigInt(k - x.k);
  const ay = y.a << BigInt(k - y.k);
  const by = y.b << BigInt(k - y.k);
  return q2SignAligned(ax - ay, bx - by);
}

export function q2DivIntToQsqrt2(x: Q2Int, y: Q2Int): Qsqrt2 {
  let den = y.a * y.a - 2n * y.b * y.b;
  if (den === 0n) {
    throw new Error("singular Qsqrt2 inverse");
  }
  let na = x.a * y.a - 2n * x.b * y.b;
  let nb = -x.a * y.b + x.b * y.a;
  if (den < 0n) {
    den = -den;
    na = -na;
    nb = -nb;
  }
  const g = gcdBigint(gcdBigint(absBigint(na), absBigint(nb)), den);
  if (g > 1n) {
    na /= g;
    nb /= g;
    den /= g;
  }
  if (!isPowerOfTwoBigint(den)) {
    throw new Error("non-dyadic division result");
  }
  const denK = bitLength(den) - 1;
  const dk = x.k - y.k;
  if (dk >= 0) {
    return qsqrt2(na, nb, denK + dk);
  }
  const scale = -dk;
  return qsqrt2(na << BigInt(scale), nb << BigInt(scale), denK);
}

export function div(x: Qsqrt2, y: Qsqrt2): Qsqrt2 {
  return q2DivIntToQsqrt2(toQ2Int(x), toQ2Int(y));
}

export function qsqrt2Approx(z: Qsqrt2): number {
  const scale = 2 ** (-z.k);
  return (Number(z.a) + Number(z.b) * Math.SQRT2) * scale;
}

export function pointEApprox(p: PointE): [number, number] {
  return [qsqrt2Approx(p.x), qsqrt2Approx(p.y)];
}

export function ceilDivPow2(nIn: number | bigint, k: number): bigint {
  const n = toBigintInt(nIn, "n");
  if (n <= 0n) {
    return 0n;
  }
  if (k <= 0) {
    return n;
  }
  const step = 1n << BigInt(k);
  return (n + step - 1n) / step;
}

export const ZERO = fromInt(0);
export const ONE = fromInt(1);
export const HALF = fromDyadic(1, 1);
export const INV_SQRT2 = qsqrt2(0, 1, 1);
export const SQRT2_MINUS_ONE = qsqrt2(-1, 1, 0);

export const ANGLE_COUNT = 16;

const S = SQRT2_MINUS_ONE;

export const DIRS: Array<[Qsqrt2, Qsqrt2]> = [
  [ONE, ZERO],
  [ONE, S],
  [ONE, ONE],
  [S, ONE],
  [ZERO, ONE],
  [neg(S), ONE],
  [neg(ONE), ONE],
  [neg(ONE), S],
  [neg(ONE), ZERO],
  [neg(ONE), neg(S)],
  [neg(ONE), neg(ONE)],
  [neg(S), neg(ONE)],
  [ZERO, neg(ONE)],
  [S, neg(ONE)],
  [ONE, neg(ONE)],
  [ONE, neg(S)],
];

export const DIRS_F: Array<[number, number]> = DIRS.map(([dx, dy]) => [
  qsqrt2Approx(dx),
  qsqrt2Approx(dy),
]);

export const DIRS_UNIT_F: Array<[number, number]> = DIRS_F.map(([rx, ry]) => {
  const rn = Math.hypot(rx, ry);
  if (rn <= 1e-15) {
    return [0.0, 0.0];
  }
  return [rx / rn, ry / rn];
});

export function mirroredDirIdx(dirIdx: number): number {
  return (4 - dirIdx + ANGLE_COUNT) % ANGLE_COUNT;
}

