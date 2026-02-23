import { nearestDirIdx } from "./creasegen_direction";
import { GridCreaseGraph } from "./creasegen_graph";
import { isBoundaryVertex } from "./creasegen_predicates";
import { cornerConditionError, cornerLineCount, cornerScore } from "./creasegen_scoring";
import { ANGLE_COUNT } from "./qsqrt2";

function incidentDirIndices(g: GridCreaseGraph, vIdx: number): number[] {
  if (!g.incidentDirsDirty.has(vIdx)) {
    const cached = g.incidentDirsCache.get(vIdx);
    if (cached !== undefined) {
      return cached;
    }
  }
  const [vx, vy] = g.pointsF[vIdx];
  const out = new Set<number>();
  for (const u of g.adj.get(vIdx) ?? []) {
    const [ux, uy] = g.pointsF[u];
    out.add(nearestDirIdx(ux - vx, uy - vy));
  }
  const result = [...out].sort((a, b) => a - b);
  g.incidentDirsCache.set(vIdx, result);
  g.incidentDirsDirty.delete(vIdx);
  return result;
}

function sectorStepsCyclic(sortedDirs: readonly number[]): number[] {
  if (sortedDirs.length === 0) {
    return [];
  }
  const out: number[] = [];
  for (let i = 0; i < sortedDirs.length; i += 1) {
    out.push((sortedDirs[(i + 1) % sortedDirs.length] - sortedDirs[i] + ANGLE_COUNT) % ANGLE_COUNT);
  }
  return out;
}

export function kawasakiResidualFromDirs(sortedDirs: readonly number[]): number {
  const n = sortedDirs.length;
  if (n % 2 !== 0 || n === 0) {
    return Number.POSITIVE_INFINITY;
  }
  if (n === 2) {
    const d0 = Math.abs(sortedDirs[1] - sortedDirs[0]) % ANGLE_COUNT;
    const d = Math.min(d0, ANGLE_COUNT - d0);
    return d === ANGLE_COUNT / 2 ? 0.0 : Number.POSITIVE_INFINITY;
  }
  if (n < 4) {
    return Number.POSITIVE_INFINITY;
  }
  const secSteps = sectorStepsCyclic(sortedDirs);
  const target = ANGLE_COUNT / 2;
  let oddSteps = 0;
  let evenSteps = 0;
  for (let i = 0; i < secSteps.length; i += 1) {
    if (i % 2 === 0) {
      oddSteps += secSteps[i];
    } else {
      evenSteps += secSteps[i];
    }
  }
  return (Math.abs(oddSteps - target) + Math.abs(evenSteps - target)) * (Math.PI / 8.0);
}

export function vertexKawasakiError(g: GridCreaseGraph, vIdx: number): number {
  if (!g.kawasakiDirty.has(vIdx)) {
    const cached = g.kawasakiCache.get(vIdx);
    if (cached !== undefined) {
      return cached;
    }
  }
  const ke = kawasakiResidualFromDirs(incidentDirIndices(g, vIdx));
  g.kawasakiCache.set(vIdx, ke);
  g.kawasakiDirty.delete(vIdx);
  return ke;
}

export function kawasakiTargetVertexIds(g: GridCreaseGraph): number[] {
  return [...g.activeVertices]
    .filter((v) => !isBoundaryVertex(g, v))
    .sort((a, b) => a - b);
}

export function kawasakiScore(
  g: GridCreaseGraph,
  opts?: {
    tol?: number;
  },
): [number, number, number] {
  const tol = opts?.tol ?? 1e-8;
  const targets = kawasakiTargetVertexIds(g);
  let bad = 0;
  let total = 0.0;
  for (const v of targets) {
    const ke = vertexKawasakiError(g, v);
    const val = Number.isFinite(ke) ? ke : 1000.0;
    total += val;
    if (val > tol) {
      bad += 1;
    }
  }
  return [bad, total, targets.length];
}

export function globalScore(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines?: number;
    kawasakiTol?: number;
  },
): [number, number, number, number, number, number] {
  const cs = cornerScore(g, cornerIds, {
    maxDeg: opts.maxDeg,
    minCornerLines: opts.minCornerLines ?? 2,
  });
  const ks = kawasakiScore(g, {
    tol: opts.kawasakiTol ?? 1e-8,
  });
  return [ks[0], cs[0], cs[1], ks[1], cs[2], cs[3]];
}

export function priorityCornerKawasakiScore(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts?: {
    tol?: number;
  },
): [number, number] {
  const tol = opts?.tol ?? 1e-8;
  let bad = 0;
  let total = 0.0;
  for (const v of cornerIds) {
    if (!g.activeVertices.has(v)) {
      continue;
    }
    if (isBoundaryVertex(g, v)) {
      continue;
    }
    const ke = vertexKawasakiError(g, v);
    const val = Number.isFinite(ke) ? ke : 1000.0;
    total += val;
    if (val > tol) {
      bad += 1;
    }
  }
  return [bad, total];
}

export function preserveSatisfiedCorners(
  beforeG: GridCreaseGraph,
  afterG: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines: number;
    tol?: number;
  },
): boolean {
  const tol = opts.tol ?? 1e-12;
  for (const v of cornerIds) {
    if (!beforeG.activeVertices.has(v) || !afterG.activeVertices.has(v)) {
      continue;
    }
    const beforeOk =
      cornerConditionError(beforeG, v, opts.maxDeg) <= tol &&
      cornerLineCount(beforeG, v) >= opts.minCornerLines;
    if (!beforeOk) {
      continue;
    }
    if (cornerConditionError(afterG, v, opts.maxDeg) > tol) {
      return false;
    }
    if (cornerLineCount(afterG, v) < opts.minCornerLines) {
      return false;
    }
  }
  return true;
}

export function violatingVertexPriority(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines: number;
    kawasakiTol: number;
  },
): number[] {
  const cset = new Set(cornerIds);
  const cand = new Set<number>();
  for (const v of cornerIds) {
    if (cornerConditionError(g, v, opts.maxDeg) > 1e-12) {
      cand.add(v);
    }
    if (cornerLineCount(g, v) < opts.minCornerLines) {
      cand.add(v);
    }
  }
  for (const v of kawasakiTargetVertexIds(g)) {
    if (vertexKawasakiError(g, v) > opts.kawasakiTol) {
      cand.add(v);
    }
  }

  const interiorCorners = cornerIds.filter((v) => !isBoundaryVertex(g, v));
  const interiorCornersAllSatisfied = interiorCorners.every(
    (v) =>
      cornerConditionError(g, v, opts.maxDeg) <= 1e-12 &&
      cornerLineCount(g, v) >= opts.minCornerLines,
  );

  function priorityGroup(v: number): number {
    const isCorner = cset.has(v);
    const isBoundaryCorner = isCorner && isBoundaryVertex(g, v);
    if (interiorCornersAllSatisfied) {
      if (isBoundaryCorner) {
        return 0;
      }
      return !isCorner ? 1 : 2;
    }
    return !isCorner ? 0 : 1;
  }

  const out = [...cand];
  out.sort((lhs, rhs) => {
    const pgL = priorityGroup(lhs);
    const pgR = priorityGroup(rhs);
    if (pgL !== pgR) {
      return pgL - pgR;
    }
    const bL = isBoundaryVertex(g, lhs) ? 1 : 0;
    const bR = isBoundaryVertex(g, rhs) ? 1 : 0;
    if (bL !== bR) {
      return bL - bR;
    }
    const kL = vertexKawasakiError(g, lhs);
    const kR = vertexKawasakiError(g, rhs);
    if (kL !== kR) {
      return kR - kL;
    }
    const cL = cornerConditionError(g, lhs, opts.maxDeg);
    const cR = cornerConditionError(g, rhs, opts.maxDeg);
    if (cL !== cR) {
      return cR - cL;
    }
    const dL = Math.max(0, opts.minCornerLines - cornerLineCount(g, lhs));
    const dR = Math.max(0, opts.minCornerLines - cornerLineCount(g, rhs));
    if (dL !== dR) {
      return dR - dL;
    }
    return lhs - rhs;
  });
  return out;
}
