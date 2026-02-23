import { ANGLE_COUNT, DIRS_F, DIRS_UNIT_F } from "./qsqrt2";

const TWO_PI = 2.0 * Math.PI;
const NEAREST_DIR_CACHE_LIMIT = 1 << 15;
const nearestDirCache = new Map<string, number>();

function normAngle(a: number): number {
  let out = a % TWO_PI;
  if (out < 0.0) {
    out += TWO_PI;
  }
  return out;
}

export function crossF(ax: number, ay: number, bx: number, by: number): number {
  return ax * by - ay * bx;
}

export function angleOfDirIdx(d: number): number {
  const [dx, dy] = DIRS_F[d];
  return normAngle(Math.atan2(dy, dx));
}

export function inCcwInterval(
  a: number,
  start: number,
  end: number,
  tol = 1e-10,
): boolean {
  const aa = normAngle(a);
  const ss = normAngle(start);
  const ee = normAngle(end);
  if (ss <= ee) {
    return ss - tol <= aa && aa <= ee + tol;
  }
  return aa >= ss - tol || aa <= ee + tol;
}

export function nearestDirIdx(dx: number, dy: number): number {
  if (Math.abs(dx) + Math.abs(dy) <= 1e-15) {
    return 0;
  }
  const key = `${dx.toPrecision(16)},${dy.toPrecision(16)}`;
  const cached = nearestDirCache.get(key);
  if (cached !== undefined) {
    return cached;
  }
  let bestK = 0;
  let bestDot = -1e100;
  for (let k = 0; k < DIRS_UNIT_F.length; k += 1) {
    const [ux, uy] = DIRS_UNIT_F[k];
    const dot = dx * ux + dy * uy;
    if (dot > bestDot) {
      bestDot = dot;
      bestK = k;
    }
  }
  if (nearestDirCache.size >= NEAREST_DIR_CACHE_LIMIT) {
    nearestDirCache.clear();
  }
  nearestDirCache.set(key, bestK);
  return bestK;
}

export function reflectedDirIdx(
  curD: number,
  a: [number, number],
  b: [number, number],
): number {
  let tx = b[0] - a[0];
  let ty = b[1] - a[1];
  const n = Math.hypot(tx, ty);
  if (n <= 1e-15) {
    return curD;
  }
  tx /= n;
  ty /= n;
  const [vx, vy] = DIRS_F[curD];
  const dot = vx * tx + vy * ty;
  const rx = vx - 2.0 * dot * tx;
  const ry = vy - 2.0 * dot * ty;
  return nearestDirIdx(rx, ry);
}

export function reflectedDirIdxByAxisDir(curD: number, axisD: number): number {
  let [tx, ty] = DIRS_F[axisD];
  const n = Math.hypot(tx, ty);
  if (n <= 1e-15) {
    return curD;
  }
  tx /= n;
  ty /= n;
  const [vx, vy] = DIRS_F[curD];
  const dot = vx * tx + vy * ty;
  const rx = vx - 2.0 * dot * tx;
  const ry = vy - 2.0 * dot * ty;
  return nearestDirIdx(rx, ry);
}

export function symmetricCandidateDirs(
  usedDirs: readonly number[],
  admissible: readonly number[],
  incomingD?: number,
): number[] {
  const used = [...new Set(usedDirs)].sort((a, b) => a - b);
  if (used.length === 0) {
    return [];
  }
  const admissibleSet = new Set(admissible);
  const out = new Set<number>();
  if (incomingD !== undefined) {
    for (const axis of used) {
      const d = reflectedDirIdxByAxisDir(incomingD, axis);
      if (admissibleSet.has(d) && !used.includes(d)) {
        out.add(d);
      }
    }
  } else {
    for (const base of used) {
      for (const axis of used) {
        const d = reflectedDirIdxByAxisDir(base, axis);
        if (admissibleSet.has(d) && !used.includes(d)) {
          out.add(d);
        }
      }
    }
  }
  return [...out].sort((a, b) => a - b);
}

export function dirGapSteps(a: number, b: number): number {
  const d = Math.abs(a - b) % ANGLE_COUNT;
  return Math.min(d, ANGLE_COUNT - d);
}
