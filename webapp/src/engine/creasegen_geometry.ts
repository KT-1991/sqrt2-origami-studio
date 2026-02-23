import { crossF } from "./creasegen_direction";

export function raySegmentHitFloat(
  origin: [number, number],
  d: [number, number],
  a: [number, number],
  b: [number, number],
  eps = 1e-12,
): [number, number] | null {
  const [ox, oy] = origin;
  const [dx, dy] = d;
  const [ax, ay] = a;
  const [bx, by] = b;
  const vx = bx - ax;
  const vy = by - ay;
  const denom = dx * vy - dy * vx;
  if (-eps <= denom && denom <= eps) {
    return null;
  }

  const wx = ax - ox;
  const wy = ay - oy;
  const t = (wx * vy - wy * vx) / denom;
  if (t <= eps) {
    return null;
  }

  const u = (wx * dy - wy * dx) / denom;
  if (u < -eps || u > 1.0 + eps) {
    return null;
  }
  return [t, u];
}

export function raySegmentHitTFloat(
  origin: [number, number],
  d: [number, number],
  a: [number, number],
  b: [number, number],
  eps = 1e-12,
): number | null {
  const hit = raySegmentHitFloat(origin, d, a, b, eps);
  if (hit === null) {
    return null;
  }
  return hit[0];
}

export function isPointOnLine(
  a: [number, number],
  b: [number, number],
  p: [number, number],
  tol = 1e-8,
): boolean {
  const abx = b[0] - a[0];
  const aby = b[1] - a[1];
  const apx = p[0] - a[0];
  const apy = p[1] - a[1];
  return Math.abs(crossF(abx, aby, apx, apy)) <= tol;
}

export function strictSegmentsIntersect(
  a1: [number, number],
  a2: [number, number],
  b1: [number, number],
  b2: [number, number],
  eps = 1e-10,
): boolean {
  function orient(
    p: [number, number],
    q: [number, number],
    r: [number, number],
  ): number {
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
  }
  const o1 = orient(a1, a2, b1);
  const o2 = orient(a1, a2, b2);
  const o3 = orient(b1, b2, a1);
  const o4 = orient(b1, b2, a2);
  return o1 * o2 < -eps && o3 * o4 < -eps;
}

export function collinearOverlapLength(
  a1: [number, number],
  a2: [number, number],
  b1: [number, number],
  b2: [number, number],
  eps = 1e-10,
): number {
  const abx = a2[0] - a1[0];
  const aby = a2[1] - a1[1];
  if (Math.abs(crossF(abx, aby, b1[0] - a1[0], b1[1] - a1[1])) > eps) {
    return 0.0;
  }
  if (Math.abs(crossF(abx, aby, b2[0] - a1[0], b2[1] - a1[1])) > eps) {
    return 0.0;
  }
  if (Math.abs(abx) >= Math.abs(aby)) {
    const [x1, x2] = a1[0] <= a2[0] ? [a1[0], a2[0]] : [a2[0], a1[0]];
    const [y1, y2] = b1[0] <= b2[0] ? [b1[0], b2[0]] : [b2[0], b1[0]];
    const lo = Math.max(x1, y1);
    const hi = Math.min(x2, y2);
    return Math.max(0.0, hi - lo);
  }
  const [x1, x2] = a1[1] <= a2[1] ? [a1[1], a2[1]] : [a2[1], a1[1]];
  const [y1, y2] = b1[1] <= b2[1] ? [b1[1], b2[1]] : [b2[1], b1[1]];
  const lo = Math.max(x1, y1);
  const hi = Math.min(x2, y2);
  return Math.max(0.0, hi - lo);
}

export interface ExistingEdgesView {
  readonly pointsF: Array<[number, number]>;
  iterEdges(): Iterable<[number, number]>;
}

export function crossesExistingEdges(
  g: ExistingEdgesView,
  i: number,
  j: number,
): boolean {
  const ai = g.pointsF[i];
  const bj = g.pointsF[j];
  for (const [u, v] of g.iterEdges()) {
    if (u === i || u === j || v === i || v === j) {
      continue;
    }
    const pu = g.pointsF[u];
    const pv = g.pointsF[v];
    if (strictSegmentsIntersect(ai, bj, pu, pv)) {
      return true;
    }
  }
  return false;
}
