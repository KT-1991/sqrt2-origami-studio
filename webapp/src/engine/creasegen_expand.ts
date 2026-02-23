import {
  angleOfDirIdx,
  dirGapSteps,
  inCcwInterval,
  nearestDirIdx,
} from "./creasegen_direction";
import { kawasakiResidualFromDirs } from "./creasegen_evaluation";
import type { GridCreaseGraph } from "./creasegen_graph";
import { pointKey, requiredGridBoundsForPoint } from "./creasegen_grid_utils";
import { isBoundaryVertex, onDiagVertex } from "./creasegen_predicates";
import {
  cornerConditionError,
  cornerLineCount,
  incidentAngles,
  interiorWedge,
  normAngle,
  requiredCornerLines,
  uniqueAngles,
} from "./creasegen_scoring";
import { ANGLE_COUNT, DIRS_F, ceilDivPow2, mirroredDirIdx } from "./qsqrt2";

function compareTuple(a: readonly number[], b: readonly number[]): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    if (a[i] < b[i]) {
      return -1;
    }
    if (a[i] > b[i]) {
      return 1;
    }
  }
  if (a.length < b.length) {
    return -1;
  }
  if (a.length > b.length) {
    return 1;
  }
  return 0;
}

function toSafeNonNegativeInt(x: bigint): number {
  if (x <= 0n) {
    return 0;
  }
  const n = Number(x);
  if (!Number.isSafeInteger(n)) {
    return Number.MAX_SAFE_INTEGER;
  }
  return n;
}

function edgeDirFrom(g: GridCreaseGraph, vIdx: number, uIdx: number): number {
  const bucket = g.edgeDirBucketAt(vIdx, uIdx);
  if (bucket !== undefined && bucket !== null) {
    const [vx, vy] = g.pointsF[vIdx];
    const [ux, uy] = g.pointsF[uIdx];
    const dx = ux - vx;
    const dy = uy - vy;
    const [bx, by] = DIRS_F[bucket];
    if (dx * bx + dy * by >= 0.0) {
      return bucket;
    }
    return (bucket + ANGLE_COUNT / 2) % ANGLE_COUNT;
  }
  const [vx, vy] = g.pointsF[vIdx];
  const [ux, uy] = g.pointsF[uIdx];
  return nearestDirIdx(ux - vx, uy - vy);
}

export function usedDirIndices(
  g: GridCreaseGraph,
  vIdx: number,
  includeBoundary = false,
): Set<number> {
  const out = new Set<number>();
  for (const u of g.adj.get(vIdx) ?? []) {
    if (!includeBoundary && g.isBoundaryEdge(vIdx, u)) {
      continue;
    }
    out.add(edgeDirFrom(g, vIdx, u));
  }
  return out;
}

export function admissibleDirsForVertex(
  g: GridCreaseGraph,
  vIdx: number,
  enforceSymmetry: boolean,
): number[] {
  let dirs = Array.from({ length: ANGLE_COUNT }, (_, i) => i);
  const [px, py] = g.pointsF[vIdx];
  const [start, width] = interiorWedge(px, py, 1e-10);
  if (width < 2.0 * Math.PI - 1e-10) {
    const end = start + width;
    dirs = dirs.filter((d) => inCcwInterval(angleOfDirIdx(d), start, end));
  }
  if (enforceSymmetry && onDiagVertex(g, vIdx)) {
    const out: number[] = [];
    const seen = new Set<string>();
    for (const d of dirs) {
      const md = mirroredDirIdx(d);
      const a = Math.min(d, md);
      const b = Math.max(d, md);
      const key = `${a},${b}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      if (d === md) {
        continue;
      }
      out.push(a);
    }
    dirs = out;
  }
  return dirs;
}

function topkDirsForVertex(
  g: GridCreaseGraph,
  opts: {
    vIdx: number;
    dirs: readonly number[];
    usedDirs: ReadonlySet<number>;
    k: number;
    firstHitMap?: Readonly<Record<number, number | null>>;
  },
): number[] {
  if (opts.k <= 0 || opts.dirs.length <= opts.k) {
    return [...opts.dirs];
  }
  const usedSorted = [...opts.usedDirs].sort((a, b) => a - b);
  const scored: Array<[number, number, number, number]> = [];
  for (const d of opts.dirs) {
    const local = [...new Set([...opts.usedDirs, d])].sort((a, b) => a - b);
    const ke = kawasakiResidualFromDirs(local);
    const hitV = opts.firstHitMap?.[d] ?? g.rayNextAt(opts.vIdx, d);
    const bpen = hitV !== null && hitV !== undefined && isBoundaryVertex(g, hitV) ? 1 : 0;
    const gap = usedSorted.length > 0 ? Math.min(...usedSorted.map((ud) => dirGapSteps(d, ud))) : 0;
    scored.push([ke, bpen, gap, d]);
  }
  scored.sort((lhs, rhs) => {
    if (lhs[0] !== rhs[0]) {
      return lhs[0] - rhs[0];
    }
    if (lhs[1] !== rhs[1]) {
      return lhs[1] - rhs[1];
    }
    if (lhs[2] !== rhs[2]) {
      return lhs[2] - rhs[2];
    }
    return lhs[3] - rhs[3];
  });
  return scored.slice(0, opts.k).map((s) => s[3]);
}

export function cornerConditionErrorWithAddedDir(
  g: GridCreaseGraph,
  vIdx: number,
  dirIdx: number,
  maxDeg: number,
): number {
  const [px, py] = g.pointsF[vIdx];
  const [start, width] = interiorWedge(px, py);
  let angs = uniqueAngles(incidentAngles(g, vIdx, false));
  const a = angleOfDirIdx(dirIdx);
  const t = normAngle(a - start);
  if (-1e-12 <= t && t <= width + 1e-12) {
    angs = uniqueAngles([...angs, a].sort((lhs, rhs) => lhs - rhs));
  }

  let ts: number[] = [0.0, width];
  for (const aa of angs) {
    const tt = normAngle(aa - start);
    if (-1e-12 <= tt && tt <= width + 1e-12) {
      ts.push(Math.min(Math.max(tt, 0.0), width));
    }
  }
  ts = uniqueAngles(ts.sort((lhs, rhs) => lhs - rhs));
  const sectors: number[] = [];
  if (ts.length > 1) {
    if (width >= 2.0 * Math.PI - 1e-10) {
      for (let i = 0; i < ts.length; i += 1) {
        let d = ts[(i + 1) % ts.length] - ts[i];
        if (d <= 0.0) {
          d += 2.0 * Math.PI;
        }
        sectors.push(d);
      }
    } else {
      for (let i = 0; i < ts.length - 1; i += 1) {
        sectors.push(ts[i + 1] - ts[i]);
      }
    }
  }
  const thr = (maxDeg * Math.PI) / 180.0;
  return sectors.reduce((acc, s) => acc + Math.max(0.0, s - thr), 0.0);
}

export interface ExpandRequest {
  needA: number;
  needB: number;
  needK: number;
  needANorm: number;
  needBNorm: number;
}

export interface ExpandNeed extends ExpandRequest {
  needCount: number;
  needCornerV: number;
  needCornerD: number;
  reason: "round_missing_grid" | "grid_required_corner";
}

export interface ExpandTarget {
  targetA: number;
  targetB: number;
  targetK: number;
  targetANorm: number;
  targetBNorm: number;
}

export function requiredNormBoundsFromGridBounds(
  aMax: number,
  bMax: number,
  k: number,
): { aNorm: number; bNorm: number } {
  const kClamped = Math.max(0, k);
  const aNorm = toSafeNonNegativeInt(ceilDivPow2(Math.max(0, aMax), kClamped));
  const bNorm = toSafeNonNegativeInt(ceilDivPow2(Math.max(0, bMax), kClamped));
  return { aNorm, bNorm };
}

export function mergeSearchStats(
  dst: Record<string, number>,
  src: Record<string, number> | undefined,
): void {
  if (!src) {
    return;
  }
  for (const [k, v] of Object.entries(src)) {
    if (k.startsWith("expand_need_")) {
      dst[k] = Math.max(dst[k] ?? 0, v);
    } else {
      dst[k] = (dst[k] ?? 0) + v;
    }
  }
}

export function expandRequestFromStats(
  stats: Record<string, number> | undefined,
): ExpandRequest | null {
  if (!stats) {
    return null;
  }
  const needA = stats.expand_need_a_max ?? 0;
  const needB = stats.expand_need_b_max ?? 0;
  const needK = stats.expand_need_k_max ?? 0;
  const needANorm = stats.expand_need_a_norm ?? 0;
  const needBNorm = stats.expand_need_b_norm ?? 0;
  if (needA <= 0 && needB <= 0 && needK <= 0 && needANorm <= 0 && needBNorm <= 0) {
    return null;
  }
  const hasANorm = Object.prototype.hasOwnProperty.call(stats, "expand_need_a_norm");
  const hasBNorm = Object.prototype.hasOwnProperty.call(stats, "expand_need_b_norm");
  if (!hasANorm || !hasBNorm) {
    throw new Error(
      "expand stats missing normalized bounds: expand_need_a_norm and expand_need_b_norm are required",
    );
  }
  if (needANorm < 0 || needBNorm < 0) {
    throw new Error("expand stats normalized bounds must be non-negative");
  }
  return {
    needA,
    needB,
    needK,
    needANorm,
    needBNorm,
  };
}

export function effectiveStallRounds(opts: {
  activeVertices: number;
  baseRounds: number;
  maxNodes: number;
}): number {
  const base = Math.max(1, opts.baseRounds);
  const cover = Math.max(1, opts.maxNodes);
  const approx = Math.floor((Math.max(0, opts.activeVertices) + cover - 1) / cover);
  return Math.max(1, base, Math.min(12, approx));
}

function singleRayGrowthProbe(
  g: GridCreaseGraph,
  originV: number,
  dirIdx: number,
): {
  usable: boolean;
  growthClass: number;
  req: { aMax: number; bMax: number; kMax: number } | null;
} {
  const hit = g.rayHitAt(originV, dirIdx);
  if (hit === null) {
    return { usable: false, growthClass: 2, req: null };
  }
  const [, , hitPos, p] = hit;
  if (hitPos !== 0) {
    return { usable: true, growthClass: 0, req: null };
  }
  const hitV = g.pointToId.get(pointKey(p));
  if (hitV === undefined) {
    const req = requiredGridBoundsForPoint(p);
    if (req === null) {
      return { usable: false, growthClass: 2, req: null };
    }
    return { usable: true, growthClass: 2, req };
  }
  if (g.activeVertices.has(hitV)) {
    return { usable: true, growthClass: 0, req: null };
  }
  return { usable: true, growthClass: 1, req: null };
}

function moveGrowthProbe(
  g: GridCreaseGraph,
  vIdx: number,
  dirIdx: number,
  enforceSymmetry: boolean,
): {
  usable: boolean;
  growthClass: number;
  req: { aMax: number; bMax: number; kMax: number } | null;
} {
  const base = singleRayGrowthProbe(g, vIdx, dirIdx);
  if (!base.usable) {
    return { usable: false, growthClass: 2, req: null };
  }
  if (!enforceSymmetry) {
    return base;
  }
  const mv = g.mirrorVertexIdx(vIdx);
  if (mv === null) {
    return { usable: false, growthClass: 2, req: null };
  }
  const md = mirroredDirIdx(dirIdx);
  const mirrored = singleRayGrowthProbe(g, mv, md);
  if (!mirrored.usable) {
    return { usable: false, growthClass: 2, req: null };
  }
  let req = base.req;
  if (mirrored.req !== null) {
    if (req === null) {
      req = mirrored.req;
    } else {
      req = {
        aMax: Math.max(req.aMax, mirrored.req.aMax),
        bMax: Math.max(req.bMax, mirrored.req.bMax),
        kMax: Math.max(req.kMax, mirrored.req.kMax),
      };
    }
  }
  return {
    usable: true,
    growthClass: Math.max(base.growthClass, mirrored.growthClass),
    req,
  };
}

function bestExpandMoveForCorner(
  g: GridCreaseGraph,
  vIdx: number,
  enforceSymmetry: boolean,
): {
  dirIdx: number;
  needA: number;
  needB: number;
  needK: number;
  needANorm: number;
  needBNorm: number;
} | null {
  if (!g.activeVertices.has(vIdx)) {
    return null;
  }
  const used = usedDirIndices(g, vIdx, false);
  const admissible = admissibleDirsForVertex(g, vIdx, enforceSymmetry);
  let bestKey: number[] | null = null;
  let bestOut:
    | {
        dirIdx: number;
        needA: number;
        needB: number;
        needK: number;
        needANorm: number;
        needBNorm: number;
      }
    | null = null;

  for (const d of admissible) {
    if (used.has(d)) {
      continue;
    }
    const probe = moveGrowthProbe(g, vIdx, d, enforceSymmetry);
    if (!probe.usable || probe.growthClass <= 1 || probe.req === null) {
      continue;
    }
    const norm = requiredNormBoundsFromGridBounds(
      probe.req.aMax,
      probe.req.bMax,
      probe.req.kMax,
    );
    const key = [
      probe.req.kMax,
      Math.max(norm.aNorm, norm.bNorm),
      norm.aNorm + norm.bNorm,
      Math.max(probe.req.aMax, probe.req.bMax),
      probe.req.aMax + probe.req.bMax,
      probe.req.aMax,
      probe.req.bMax,
      d,
    ];
    if (bestKey === null || compareTuple(key, bestKey) < 0) {
      bestKey = key;
      bestOut = {
        dirIdx: d,
        needA: probe.req.aMax,
        needB: probe.req.bMax,
        needK: probe.req.kMax,
        needANorm: norm.aNorm,
        needBNorm: norm.bNorm,
      };
    }
  }
  return bestOut;
}

function gridRequiredCornerExpandRequest(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines: number;
    enforceSymmetry: boolean;
  },
): ExpandNeed | null {
  const required: Array<{
    v: number;
    needA: number;
    needB: number;
    needK: number;
    needANorm: number;
    needBNorm: number;
    hasNonexpandMove: number;
    dirIdx: number;
  }> = [];

  for (const v of cornerIds) {
    if (!g.activeVertices.has(v)) {
      continue;
    }
    const needCorner = cornerConditionError(g, v, opts.maxDeg) > 1e-12;
    const needLines =
      cornerLineCount(g, v) <
      requiredCornerLines(g, v, {
        maxDeg: opts.maxDeg,
        minCornerLines: opts.minCornerLines,
      });
    if (!needCorner && !needLines) {
      continue;
    }

    const used = usedDirIndices(g, v, false);
    const admissible = admissibleDirsForVertex(g, v, opts.enforceSymmetry);
    let hasNonexpandMove = false;
    const reqs: Array<{
      needA: number;
      needB: number;
      needK: number;
      needANorm: number;
      needBNorm: number;
      dirIdx: number;
    }> = [];

    for (const d of admissible) {
      if (used.has(d)) {
        continue;
      }
      const probe = moveGrowthProbe(g, v, d, opts.enforceSymmetry);
      if (!probe.usable) {
        continue;
      }
      if (probe.growthClass <= 1) {
        hasNonexpandMove = true;
        continue;
      }
      if (probe.req === null) {
        continue;
      }
      const norm = requiredNormBoundsFromGridBounds(
        probe.req.aMax,
        probe.req.bMax,
        probe.req.kMax,
      );
      reqs.push({
        needA: probe.req.aMax,
        needB: probe.req.bMax,
        needK: probe.req.kMax,
        needANorm: norm.aNorm,
        needBNorm: norm.bNorm,
        dirIdx: d,
      });
    }

    if (reqs.length === 0) {
      continue;
    }
    reqs.sort((lhs, rhs) =>
      compareTuple(
        [
          lhs.needK,
          Math.max(lhs.needANorm, lhs.needBNorm),
          lhs.needANorm + lhs.needBNorm,
          Math.max(lhs.needA, lhs.needB),
          lhs.needA + lhs.needB,
          lhs.needA,
          lhs.needB,
          lhs.dirIdx,
        ],
        [
          rhs.needK,
          Math.max(rhs.needANorm, rhs.needBNorm),
          rhs.needANorm + rhs.needBNorm,
          Math.max(rhs.needA, rhs.needB),
          rhs.needA + rhs.needB,
          rhs.needA,
          rhs.needB,
          rhs.dirIdx,
        ],
      ),
    );
    const best = reqs[0];
    required.push({
      v,
      needA: best.needA,
      needB: best.needB,
      needK: best.needK,
      needANorm: best.needANorm,
      needBNorm: best.needBNorm,
      hasNonexpandMove: hasNonexpandMove ? 1 : 0,
      dirIdx: best.dirIdx,
    });
  }

  if (required.length === 0) {
    return null;
  }

  required.sort((lhs, rhs) =>
    compareTuple(
      [
        lhs.hasNonexpandMove,
        lhs.needK,
        Math.max(lhs.needANorm, lhs.needBNorm),
        lhs.needANorm + lhs.needBNorm,
        Math.max(lhs.needA, lhs.needB),
        lhs.needA + lhs.needB,
        lhs.needA,
        lhs.needB,
        lhs.v,
        lhs.dirIdx,
      ],
      [
        rhs.hasNonexpandMove,
        rhs.needK,
        Math.max(rhs.needANorm, rhs.needBNorm),
        rhs.needANorm + rhs.needBNorm,
        Math.max(rhs.needA, rhs.needB),
        rhs.needA + rhs.needB,
        rhs.needA,
        rhs.needB,
        rhs.v,
        rhs.dirIdx,
      ],
    ),
  );

  const best = required[0];
  return {
    needA: best.needA,
    needB: best.needB,
    needK: best.needK,
    needANorm: best.needANorm,
    needBNorm: best.needBNorm,
    needCount: required.length,
    needCornerV: best.v,
    needCornerD: best.dirIdx,
    reason: "grid_required_corner",
  };
}

function boundaryCornerPromisingExpandTargets(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines: number;
    enforceSymmetry: boolean;
  },
): number[] {
  const out: number[] = [];
  for (const v of cornerIds) {
    if (!g.activeVertices.has(v) || !isBoundaryVertex(g, v)) {
      continue;
    }
    const beforeErr = cornerConditionError(g, v, opts.maxDeg);
    const beforeLines = cornerLineCount(g, v);
    const needLines = requiredCornerLines(g, v, {
      maxDeg: opts.maxDeg,
      minCornerLines: opts.minCornerLines,
    });
    if (beforeErr <= 1e-12 && beforeLines >= needLines) {
      continue;
    }

    const used = usedDirIndices(g, v, false);
    const rowV = g.ensureRayNext(v);
    const feasible: number[] = [];
    const firstHit: Record<number, number | null> = {};
    for (const d of admissibleDirsForVertex(g, v, opts.enforceSymmetry)) {
      if (used.has(d)) {
        continue;
      }
      const hitV = rowV[d];
      if (hitV === null) {
        continue;
      }
      const lineImprove = beforeLines < needLines;
      const errAfter = cornerConditionErrorWithAddedDir(g, v, d, opts.maxDeg);
      const errImprove = errAfter + 1e-12 < beforeErr;
      if (!lineImprove && !errImprove) {
        continue;
      }
      feasible.push(d);
      firstHit[d] = hitV;
    }
    if (feasible.length === 0) {
      continue;
    }
    const checkDirs = topkDirsForVertex(g, {
      vIdx: v,
      dirs: feasible,
      usedDirs: used,
      k: Math.min(4, feasible.length),
      firstHitMap: firstHit,
    });
    if (checkDirs.length > 0) {
      out.push(v);
    }
  }
  return out;
}

export function detectExpandNeed(
  g: GridCreaseGraph,
  opts: {
    cornerIds: readonly number[];
    roundStats: Record<string, number>;
    cornerMaxDeg: number;
    minCornerLines: number;
    enforceSymmetry: boolean;
    searchStats: Record<string, number>;
  },
): ExpandNeed | null {
  const promisingBoundary = boundaryCornerPromisingExpandTargets(g, opts.cornerIds, {
    maxDeg: opts.cornerMaxDeg,
    minCornerLines: opts.minCornerLines,
    enforceSymmetry: opts.enforceSymmetry,
  });
  const reqStats = expandRequestFromStats(opts.roundStats);
  if (reqStats !== null && promisingBoundary.length > 0) {
    const needCornerV = promisingBoundary[0];
    let needCornerD = -1;
    const sel = bestExpandMoveForCorner(g, needCornerV, opts.enforceSymmetry);
    if (sel !== null) {
      needCornerD = sel.dirIdx;
    }
    opts.searchStats.round_missing_grid_expand_detect =
      (opts.searchStats.round_missing_grid_expand_detect ?? 0) + 1;
    opts.searchStats.round_missing_grid_corner_count_max = Math.max(
      opts.searchStats.round_missing_grid_corner_count_max ?? 0,
      promisingBoundary.length,
    );
    return {
      ...reqStats,
      needCount: promisingBoundary.length,
      needCornerV,
      needCornerD,
      reason: "round_missing_grid",
    };
  }

  const req = gridRequiredCornerExpandRequest(g, opts.cornerIds, {
    maxDeg: opts.cornerMaxDeg,
    minCornerLines: opts.minCornerLines,
    enforceSymmetry: opts.enforceSymmetry,
  });
  if (req === null) {
    return null;
  }

  opts.searchStats.grid_required_corner_detect =
    (opts.searchStats.grid_required_corner_detect ?? 0) + 1;
  opts.searchStats.grid_required_corner_count_max = Math.max(
    opts.searchStats.grid_required_corner_count_max ?? 0,
    req.needCount,
  );
  return req;
}

export function planExpandTarget(
  need: ExpandNeed,
  opts: {
    aWork: number;
    bWork: number;
    kLocal: number;
    aNormWork: number;
    bNormWork: number;
    stagedKRelax: boolean;
  },
): ExpandTarget | null {
  let targetA = opts.aWork;
  let targetB = opts.bWork;
  let targetANorm = opts.aNormWork;
  let targetBNorm = opts.bNormWork;
  let targetK = opts.stagedKRelax ? opts.kLocal : Math.max(opts.kLocal, need.needK);

  if (need.reason === "round_missing_grid" && targetK > opts.kLocal) {
    targetK = Math.min(targetK, opts.kLocal + 1);
  }

  if (need.reason === "round_missing_grid") {
    targetA = Math.max(opts.aWork, Math.min(need.needA, opts.aWork + 1));
    targetB = Math.max(opts.bWork, Math.min(need.needB, opts.bWork + 1));
    targetANorm = Math.max(opts.aNormWork, Math.min(need.needANorm, opts.aNormWork + 1));
    targetBNorm = Math.max(opts.bNormWork, Math.min(need.needBNorm, opts.bNormWork + 1));
  } else {
    targetA = Math.max(opts.aWork, need.needA);
    targetB = Math.max(opts.bWork, need.needB);
    targetANorm = Math.max(opts.aNormWork, need.needANorm);
    targetBNorm = Math.max(opts.bNormWork, need.needBNorm);
  }

  targetA = Math.max(targetA, targetANorm << targetK);
  targetB = Math.max(targetB, targetBNorm << targetK);
  if (
    targetA <= opts.aWork &&
    targetB <= opts.bWork &&
    targetK <= opts.kLocal &&
    targetANorm <= opts.aNormWork &&
    targetBNorm <= opts.bNormWork
  ) {
    return null;
  }

  return {
    targetA,
    targetB,
    targetK,
    targetANorm,
    targetBNorm,
  };
}

export function expandMode(
  target: ExpandTarget,
  opts: {
    curA: number;
    curB: number;
    curK: number;
    curANorm: number;
    curBNorm: number;
  },
): "k_only" | "with_ab" {
  const kChanged = target.targetK > opts.curK;
  const abChanged = target.targetA > opts.curA || target.targetB > opts.curB;
  const normChanged = target.targetANorm > opts.curANorm || target.targetBNorm > opts.curBNorm;
  if (kChanged && !abChanged && !normChanged) {
    return "k_only";
  }
  return "with_ab";
}
