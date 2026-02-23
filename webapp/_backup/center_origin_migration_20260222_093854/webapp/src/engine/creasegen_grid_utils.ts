import type { PointE, Qsqrt2 } from "./types";
import { ceilDivPow2, q2Cmp, ONE, ZERO } from "./qsqrt2";

export const MASK64 = (1n << 64n) - 1n;

function absBigint(x: bigint): bigint {
  return x < 0n ? -x : x;
}

function bigintToSafeInt(x: bigint): number | null {
  const n = Number(x);
  if (!Number.isSafeInteger(n)) {
    return null;
  }
  return n;
}

export function inSquare(p: PointE): boolean {
  return (
    q2Cmp(p.x, ZERO) >= 0 &&
    q2Cmp(p.x, ONE) <= 0 &&
    q2Cmp(p.y, ZERO) >= 0 &&
    q2Cmp(p.y, ONE) <= 0
  );
}

export function pointKey(p: PointE): string {
  return `${p.x.a},${p.x.b},${p.x.k},${p.y.a},${p.y.b},${p.y.k}`;
}

export function splitmix64(x: bigint): bigint {
  let z = (x + 0x9e3779b97f4a7c15n) & MASK64;
  z = ((z ^ (z >> 30n)) * 0xbf58476d1ce4e5b9n) & MASK64;
  z = ((z ^ (z >> 27n)) * 0x94d049bb133111ebn) & MASK64;
  return (z ^ (z >> 31n)) & MASK64;
}

export function edgeHashPair(i: number, j: number): [bigint, bigint] {
  const a = i < j ? i : j;
  const b = i < j ? j : i;
  const x = ((BigInt(a) & 0xffffffffn) << 32n) | (BigInt(b) & 0xffffffffn);
  const h1 = splitmix64(x ^ 0xd6e8feb86659fd93n);
  const h2 = splitmix64(x ^ 0xa5a3564e27f8865bn);
  return [h1, h2];
}

export function pointKLevel(p: PointE): number {
  return Math.max(p.x.k, p.y.k);
}

export interface RequiredBounds {
  k: number;
  absA: number;
  absB: number;
}

export function requiredBoundsForQsqrt2(z: Qsqrt2): RequiredBounds | null {
  const absA = bigintToSafeInt(absBigint(z.a));
  const absB = bigintToSafeInt(absBigint(z.b));
  if (absA === null || absB === null) {
    return null;
  }
  return { k: z.k, absA, absB };
}

export interface RequiredGridBounds {
  aMax: number;
  bMax: number;
  kMax: number;
}

export function requiredGridBoundsForPoint(p: PointE): RequiredGridBounds | null {
  const bx = requiredBoundsForQsqrt2(p.x);
  const by = requiredBoundsForQsqrt2(p.y);
  if (bx === null || by === null) {
    return null;
  }
  return {
    aMax: Math.max(bx.absA, by.absA),
    bMax: Math.max(bx.absB, by.absB),
    kMax: Math.max(bx.k, by.k),
  };
}

export interface RequiredNormBounds {
  aNorm: number;
  bNorm: number;
}

export function requiredNormBoundsForPoint(p: PointE): RequiredNormBounds | null {
  const bx = requiredBoundsForQsqrt2(p.x);
  const by = requiredBoundsForQsqrt2(p.y);
  if (bx === null || by === null) {
    return null;
  }
  const ax = bigintToSafeInt(ceilDivPow2(BigInt(bx.absA), bx.k));
  const bxn = bigintToSafeInt(ceilDivPow2(BigInt(bx.absB), bx.k));
  const ay = bigintToSafeInt(ceilDivPow2(BigInt(by.absA), by.k));
  const byn = bigintToSafeInt(ceilDivPow2(BigInt(by.absB), by.k));
  if (ax === null || bxn === null || ay === null || byn === null) {
    return null;
  }
  return {
    aNorm: Math.max(ax, ay),
    bNorm: Math.max(bxn, byn),
  };
}

export function recordMissingPointStats(
  stats: Record<string, number> | undefined,
  p: PointE,
): void {
  if (!stats) {
    return;
  }
  stats.reject_missing_grid_point = (stats.reject_missing_grid_point ?? 0) + 1;
  const req = requiredGridBoundsForPoint(p);
  if (req === null) {
    stats.reject_missing_grid_point_unknown =
      (stats.reject_missing_grid_point_unknown ?? 0) + 1;
    return;
  }
  stats.expand_need_a_max = Math.max(stats.expand_need_a_max ?? 0, req.aMax);
  stats.expand_need_b_max = Math.max(stats.expand_need_b_max ?? 0, req.bMax);
  stats.expand_need_k_max = Math.max(stats.expand_need_k_max ?? 0, req.kMax);
  const reqNorm = requiredNormBoundsForPoint(p);
  if (reqNorm !== null) {
    stats.expand_need_a_norm = Math.max(stats.expand_need_a_norm ?? 0, reqNorm.aNorm);
    stats.expand_need_b_norm = Math.max(stats.expand_need_b_norm ?? 0, reqNorm.bNorm);
  }
}

export function mirrorPointYEqX(p: PointE): PointE {
  return {
    x: p.y,
    y: p.x,
  };
}
