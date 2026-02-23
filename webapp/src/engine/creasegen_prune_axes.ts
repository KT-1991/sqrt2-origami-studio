import {
  globalScore,
  kawasakiScore,
  priorityCornerKawasakiScore,
  vertexKawasakiError,
} from "./creasegen_evaluation";
import { nearestDirIdx } from "./creasegen_direction";
import type { GridCreaseGraph } from "./creasegen_graph";
import { cloneGraph } from "./creasegen_graph_ops";
import { diagonalSymmetryOk, isBoundaryVertex } from "./creasegen_predicates";
import { PAPER_CENTER_F } from "./paper_frame";
import { ANGLE_COUNT, DIRS, DIRS_F, DIRS_UNIT_F, mul, sub } from "./qsqrt2";

function normEdge(i: number, j: number): [number, number] {
  return i < j ? [i, j] : [j, i];
}

function edgeKey(i: number, j: number): string {
  const [a, b] = normEdge(i, j);
  return `${a},${b}`;
}

function edgeFromKey(key: string): [number, number] {
  const idx = key.indexOf(",");
  return [Number(key.slice(0, idx)), Number(key.slice(idx + 1))];
}

function edgeBirth(g: GridCreaseGraph, e: readonly [number, number]): number {
  return g.edgeBirthOrder(e[0], e[1]) ?? -1;
}

function edgeDirFrom(g: GridCreaseGraph, i: number, j: number): number | null {
  const bucket = g.edgeDirBucketAt(i, j);
  if (bucket !== null && bucket !== undefined) {
    const [vx, vy] = g.pointsF[i];
    const [ux, uy] = g.pointsF[j];
    const [bx, by] = DIRS_F[bucket];
    const dx = ux - vx;
    const dy = uy - vy;
    if (dx * bx + dy * by >= 0.0) {
      return bucket;
    }
    return (bucket + ANGLE_COUNT / 2) % ANGLE_COUNT;
  }
  const [vx, vy] = g.pointsF[i];
  const [ux, uy] = g.pointsF[j];
  if (Math.abs(ux - vx) + Math.abs(uy - vy) <= 1e-15) {
    return null;
  }
  return nearestDirIdx(ux - vx, uy - vy);
}

function crossF(ax: number, ay: number, bx: number, by: number): number {
  return ax * by - ay * bx;
}

function compareNumericTuple(a: readonly number[], b: readonly number[]): number {
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

export interface PruneLineKey {
  axis: number;
  a: bigint;
  b: bigint;
  k: number;
}

export interface AxisCycleTarget {
  lineKey: PruneLineKey;
  representativeEdge: [number, number];
  cycleLen: number;
  deleteGroup: Array<[number, number]>;
}

function lineKeyHash(k: PruneLineKey): string {
  return `${k.axis}|${k.a.toString()}|${k.b.toString()}|${k.k}`;
}

export function lineKeyEq(a: PruneLineKey, b: PruneLineKey): boolean {
  return a.axis === b.axis && a.a === b.a && a.b === b.b && a.k === b.k;
}

export function edgeLineKey(g: GridCreaseGraph, e: readonly [number, number]): PruneLineKey | null {
  const [a, b] = normEdge(e[0], e[1]);
  const d0 = edgeDirFrom(g, a, b);
  if (d0 === null) {
    return null;
  }
  const axis = d0 % (ANGLE_COUNT / 2);
  const p = g.points[a];
  const [rx, ry] = DIRS[axis];
  const c = sub(mul(p.x, ry), mul(p.y, rx));
  return {
    axis,
    a: c.a,
    b: c.b,
    k: c.k,
  };
}

export function edgeCenterDist2(g: GridCreaseGraph, e: readonly [number, number]): number {
  const [i, j] = normEdge(e[0], e[1]);
  const [x1, y1] = g.pointsF[i];
  const [x2, y2] = g.pointsF[j];
  const cx = 0.5 * (x1 + x2);
  const cy = 0.5 * (y1 + y2);
  return (cx - PAPER_CENTER_F) ** 2 + (cy - PAPER_CENTER_F) ** 2;
}

function buildActiveVertexLookup(
  g: GridCreaseGraph,
  scale = 10_000_000,
): Map<string, number[]> {
  const out = new Map<string, number[]>();
  for (const v of g.activeVertices) {
    const [x, y] = g.pointsF[v];
    const key = `${Math.round(x * scale)},${Math.round(y * scale)}`;
    const cur = out.get(key);
    if (cur) {
      cur.push(v);
    } else {
      out.set(key, [v]);
    }
  }
  return out;
}

function lookupActiveVertexByXY(
  g: GridCreaseGraph,
  lookup: Map<string, number[]>,
  x: number,
  y: number,
  opts?: {
    scale?: number;
    tol?: number;
  },
): number | null {
  const scale = opts?.scale ?? 10_000_000;
  const tol = opts?.tol ?? 2e-6;
  const tol2 = tol * tol;
  const kx = Math.round(x * scale);
  const ky = Math.round(y * scale);

  let bestV: number | null = null;
  let bestD2 = Number.POSITIVE_INFINITY;
  for (const dx of [-1, 0, 1]) {
    for (const dy of [-1, 0, 1]) {
      const vs = lookup.get(`${kx + dx},${ky + dy}`);
      if (!vs) {
        continue;
      }
      for (const v of vs) {
        const [vx, vy] = g.pointsF[v];
        const d2 = (vx - x) ** 2 + (vy - y) ** 2;
        if (d2 > tol2) {
          continue;
        }
        if (d2 < bestD2) {
          bestD2 = d2;
          bestV = v;
        }
      }
    }
  }
  return bestV;
}

function mirrorXYAcrossAxis(
  x: number,
  y: number,
  ax: number,
  ay: number,
  tx: number,
  ty: number,
): [number, number] {
  const vx = x - ax;
  const vy = y - ay;
  const proj = vx * tx + vy * ty;
  const fx = ax + proj * tx;
  const fy = ay + proj * ty;
  return [2.0 * fx - x, 2.0 * fy - y];
}

function signedDistToAxis(
  x: number,
  y: number,
  ax: number,
  ay: number,
  tx: number,
  ty: number,
): number {
  return crossF(tx, ty, x - ax, y - ay);
}

function edgeIsDeletable(g: GridCreaseGraph, u: number, v: number): boolean {
  return g.hasEdge(u, v) && !g.isBoundaryEdge(u, v);
}

export function bestAxisCycleGroupForLine(
  g: GridCreaseGraph,
  lineKey: PruneLineKey,
  groupEdges: ReadonlyArray<[number, number]>,
  maxPairs = 12,
): {
  cycleLen: number;
  deleteGroup: Array<[number, number]>;
  representativeEdge: [number, number];
} | null {
  interface AxisCycleCandidate {
    cycleLen: number;
    tie: number;
    deleteKeys: Set<string>;
    representativeEdge: [number, number];
  }

  if (groupEdges.length === 0) {
    return null;
  }
  const axisD = lineKey.axis;
  const [tx, ty] = DIRS_UNIT_F[axisD];
  if (Math.abs(tx) + Math.abs(ty) <= 1e-15) {
    return null;
  }

  const axisVertices = [...new Set(groupEdges.flatMap((e) => [e[0], e[1]])).values()]
    .filter((v) => g.activeVertices.has(v))
    .sort((a, b) => a - b);
  if (axisVertices.length < 2) {
    return null;
  }

  const [a0x, a0y] = g.pointsF[groupEdges[0][0]];
  const lookup = buildActiveVertexLookup(g);

  const projVs = axisVertices
    .map((v) => {
      const [x, y] = g.pointsF[v];
      return { proj: x * tx + y * ty, v };
    })
    .sort((lhs, rhs) => lhs.proj - rhs.proj);

  const pairKeys: Array<{ spanNeg: number; i: number; j: number }> = [];
  for (let i = 0; i < projVs.length; i += 1) {
    for (let j = i + 1; j < projVs.length; j += 1) {
      const span = projVs[j].proj - projVs[i].proj;
      if (span <= 1e-8) {
        continue;
      }
      pairKeys.push({ spanNeg: -span, i, j });
    }
  }
  pairKeys.sort((lhs, rhs) => lhs.spanNeg - rhs.spanNeg);
  const pairScan = pairKeys.slice(0, Math.max(0, maxPairs));

  let best: AxisCycleCandidate | null = null;

  function tryUpdate(
    cycleLen: number,
    deleteKeys: Set<string>,
    representativeEdge: [number, number],
    tie: number,
  ): void {
    const key = [cycleLen, tie];
    if (best === null || compareNumericTuple(key, [best.cycleLen, best.tie]) < 0) {
      best = {
        cycleLen,
        tie,
        deleteKeys,
        representativeEdge: normEdge(representativeEdge[0], representativeEdge[1]),
      };
    }
  }

  for (const entry of pairScan) {
    const a = projVs[entry.i].v;
    const c = projVs[entry.j].v;
    if (a === c) {
      continue;
    }
    for (const b of g.adj.get(a) ?? []) {
      if (b === c) {
        continue;
      }
      if (!edgeIsDeletable(g, a, b)) {
        continue;
      }
      const [bx, by] = g.pointsF[b];
      const sb = signedDistToAxis(bx, by, a0x, a0y, tx, ty);
      if (sb <= 1e-8) {
        continue;
      }
      const [bmx, bmy] = mirrorXYAcrossAxis(bx, by, a0x, a0y, tx, ty);
      const bm = lookupActiveVertexByXY(g, lookup, bmx, bmy);
      if (bm === null || bm === b) {
        continue;
      }
      if (!edgeIsDeletable(g, a, bm)) {
        continue;
      }

      if (edgeIsDeletable(g, b, c) && edgeIsDeletable(g, bm, c)) {
        const group4 = new Set<string>([
          edgeKey(a, b),
          edgeKey(b, c),
          edgeKey(a, bm),
          edgeKey(bm, c),
        ]);
        tryUpdate(4, group4, normEdge(a, c), 0);
      }

      for (const e of g.adj.get(b) ?? []) {
        if (e === a || e === b || e === c) {
          continue;
        }
        if (!edgeIsDeletable(g, b, e) || !edgeIsDeletable(g, e, c)) {
          continue;
        }
        const [ex, ey] = g.pointsF[e];
        const se = signedDistToAxis(ex, ey, a0x, a0y, tx, ty);
        if (se <= 1e-8) {
          continue;
        }
        const [emx, emy] = mirrorXYAcrossAxis(ex, ey, a0x, a0y, tx, ty);
        const em = lookupActiveVertexByXY(g, lookup, emx, emy);
        if (em === null || em === e || em === b || em === c) {
          continue;
        }
        if (!edgeIsDeletable(g, bm, em) || !edgeIsDeletable(g, em, c)) {
          continue;
        }
        const group6 = new Set<string>([
          edgeKey(a, b),
          edgeKey(b, e),
          edgeKey(e, c),
          edgeKey(a, bm),
          edgeKey(bm, em),
          edgeKey(em, c),
        ]);
        tryUpdate(6, group6, normEdge(a, c), 1);
      }
    }
  }

  const bestSafe = best as AxisCycleCandidate | null;
  if (bestSafe === null) {
    return null;
  }
  return {
    cycleLen: bestSafe.cycleLen,
    deleteGroup: [...bestSafe.deleteKeys].map(edgeFromKey),
    representativeEdge: bestSafe.representativeEdge,
  };
}

export function collectPruneAxisRepresentatives(
  g: GridCreaseGraph,
  maxCandidates: number,
): Array<{ edge: [number, number]; cycleLen: number }> {
  const candidates = g.edgePairs().filter((e) => !g.isBoundaryEdge(e[0], e[1]));
  const lineGroups = new Map<string, { key: PruneLineKey; edges: Array<[number, number]> }>();
  const lineRank = new Map<string, [number, number]>();

  for (const e of candidates) {
    const lk = edgeLineKey(g, e);
    if (lk === null) {
      continue;
    }
    const hash = lineKeyHash(lk);
    const cur = lineGroups.get(hash);
    if (cur) {
      cur.edges.push(normEdge(e[0], e[1]));
    } else {
      lineGroups.set(hash, { key: lk, edges: [normEdge(e[0], e[1])] });
    }
    const rk: [number, number] = [edgeCenterDist2(g, e), -edgeBirth(g, e)];
    const prv = lineRank.get(hash);
    if (!prv || compareNumericTuple(rk, prv) < 0) {
      lineRank.set(hash, rk);
    }
  }

  const ordered = [...lineGroups.keys()].sort((lhs, rhs) =>
    compareNumericTuple(lineRank.get(lhs) ?? [Number.POSITIVE_INFINITY, 0], lineRank.get(rhs) ?? [Number.POSITIVE_INFINITY, 0]),
  );
  const lineScanLimit = Math.max(maxCandidates * 6, maxCandidates);
  const targeted: Array<{ edge: [number, number]; cycleLen: number }> = [];
  for (const hash of ordered.slice(0, lineScanLimit)) {
    const group = lineGroups.get(hash);
    if (!group) {
      continue;
    }
    const best = bestAxisCycleGroupForLine(g, group.key, group.edges);
    if (best === null) {
      continue;
    }
    targeted.push({
      edge: best.representativeEdge,
      cycleLen: best.cycleLen,
    });
    if (targeted.length >= maxCandidates) {
      break;
    }
  }

  targeted.sort((lhs, rhs) =>
    compareNumericTuple(
      [
        lhs.cycleLen === 4 ? 0 : 1,
        edgeCenterDist2(g, lhs.edge),
        -edgeBirth(g, lhs.edge),
      ],
      [
        rhs.cycleLen === 4 ? 0 : 1,
        edgeCenterDist2(g, rhs.edge),
        -edgeBirth(g, rhs.edge),
      ],
    ),
  );
  return targeted;
}

export function collectAxisCycleTargets(
  g: GridCreaseGraph,
  maxCandidates: number,
): AxisCycleTarget[] {
  const candidates = g.edgePairs().filter((e) => !g.isBoundaryEdge(e[0], e[1]));
  const lineGroups = new Map<string, { key: PruneLineKey; edges: Array<[number, number]> }>();
  const lineRank = new Map<string, [number, number]>();

  for (const e of candidates) {
    const lk = edgeLineKey(g, e);
    if (lk === null) {
      continue;
    }
    const hash = lineKeyHash(lk);
    const cur = lineGroups.get(hash);
    if (cur) {
      cur.edges.push(normEdge(e[0], e[1]));
    } else {
      lineGroups.set(hash, { key: lk, edges: [normEdge(e[0], e[1])] });
    }
    const rk: [number, number] = [edgeCenterDist2(g, e), -edgeBirth(g, e)];
    const prv = lineRank.get(hash);
    if (!prv || compareNumericTuple(rk, prv) < 0) {
      lineRank.set(hash, rk);
    }
  }

  const ordered = [...lineGroups.keys()].sort((lhs, rhs) =>
    compareNumericTuple(
      lineRank.get(lhs) ?? [Number.POSITIVE_INFINITY, 0],
      lineRank.get(rhs) ?? [Number.POSITIVE_INFINITY, 0],
    ),
  );
  const lineScanLimit = Math.max(maxCandidates * 6, maxCandidates);
  const out: AxisCycleTarget[] = [];
  for (const hash of ordered.slice(0, lineScanLimit)) {
    const group = lineGroups.get(hash);
    if (!group) {
      continue;
    }
    const best = bestAxisCycleGroupForLine(g, group.key, group.edges);
    if (best === null) {
      continue;
    }
    out.push({
      lineKey: group.key,
      representativeEdge: best.representativeEdge,
      cycleLen: best.cycleLen,
      deleteGroup: best.deleteGroup,
    });
    if (out.length >= maxCandidates) {
      break;
    }
  }

  out.sort((lhs, rhs) =>
    compareNumericTuple(
      [
        lhs.cycleLen === 4 ? 0 : 1,
        edgeCenterDist2(g, lhs.representativeEdge),
        -edgeBirth(g, lhs.representativeEdge),
      ],
      [
        rhs.cycleLen === 4 ? 0 : 1,
        edgeCenterDist2(g, rhs.representativeEdge),
        -edgeBirth(g, rhs.representativeEdge),
      ],
    ),
  );
  return out;
}

function localKawasakiMetric(
  g: GridCreaseGraph,
  verts: Iterable<number>,
  tol: number,
): [number, number] {
  let bad = 0;
  let total = 0.0;
  for (const v of verts) {
    if (!g.activeVertices.has(v)) {
      continue;
    }
    if (isBoundaryVertex(g, v)) {
      continue;
    }
    const ke = vertexKawasakiError(g, v);
    const val = Number.isFinite(ke) ? ke : 1000.0;
    if (val > tol) {
      bad += 1;
    }
    total += val;
  }
  return [bad, total];
}

function clearRayHitRowUnsafe(g: GridCreaseGraph, v: number): void {
  const row = g.rayHit.get(v);
  if (!row) {
    return;
  }
  for (const hit of row) {
    if (!hit) {
      continue;
    }
    const key = edgeKey(hit[0], hit[1]);
    const vs = g.rayHitRev.get(key);
    if (!vs) {
      continue;
    }
    vs.delete(v);
    if (vs.size === 0) {
      g.rayHitRev.delete(key);
    }
  }
}

function deactivateIsolatedNoncornerVertices(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
): void {
  const cset = new Set(cornerIds);
  for (const v of [...g.activeVertices]) {
    if (cset.has(v)) {
      continue;
    }
    const deg = g.adj.get(v)?.size ?? 0;
    if (deg > 0) {
      continue;
    }
    clearRayHitRowUnsafe(g, v);
    g.activeVertices.delete(v);
    g.adj.delete(v);
    g.rayNext.delete(v);
    g.rayHit.delete(v);
    g.rayDirty.delete(v);
    g.incidentDirsCache.delete(v);
    g.incidentDirsDirty.delete(v);
    g.kawasakiCache.delete(v);
    g.kawasakiDirty.delete(v);
  }
}

export function runDeleteGroupTransaction(
  g: GridCreaseGraph,
  deleteGroup: ReadonlyArray<[number, number]>,
  cornerIds: readonly number[],
  opts: {
    enforceSymmetry: boolean;
    kawasakiTol: number;
    baselineKBad?: number;
  },
): { graph: GridCreaseGraph; removed: number } | null {
  if (deleteGroup.length === 0) {
    return null;
  }
  const normGroupKeys = new Set<string>(deleteGroup.map((e) => edgeKey(e[0], e[1])));
  for (const k of normGroupKeys) {
    const [a, b] = edgeFromKey(k);
    if (!g.hasEdge(a, b) || g.isBoundaryEdge(a, b)) {
      return null;
    }
  }

  const baseBad = opts.baselineKBad ?? kawasakiScore(g, { tol: opts.kawasakiTol })[0];
  const touched = new Set<number>();
  for (const k of normGroupKeys) {
    const [a, b] = edgeFromKey(k);
    touched.add(a);
    touched.add(b);
  }
  const [beforeBad, beforeSum] = localKawasakiMetric(g, touched, opts.kawasakiTol);

  const trial = cloneGraph(g);
  const sortedGroup = [...normGroupKeys]
    .map(edgeFromKey)
    .sort((lhs, rhs) => {
      if (lhs[0] !== rhs[0]) {
        return lhs[0] - rhs[0];
      }
      return lhs[1] - rhs[1];
    });
  for (const [a, b] of sortedGroup) {
    if (!trial.hasEdge(a, b)) {
      return null;
    }
    trial.removeEdge(a, b);
  }
  deactivateIsolatedNoncornerVertices(trial, cornerIds);
  if (opts.enforceSymmetry && !diagonalSymmetryOk(trial)) {
    return null;
  }

  const [afterBad, afterSum] = localKawasakiMetric(trial, touched, opts.kawasakiTol);
  if (afterBad > beforeBad) {
    return null;
  }
  if (afterSum > beforeSum + 1e-12) {
    return null;
  }
  if (kawasakiScore(trial, { tol: opts.kawasakiTol })[0] > baseBad) {
    return null;
  }
  return {
    graph: trial,
    removed: normGroupKeys.size,
  };
}

export function refreshGraphByPruning(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines: number;
    kawasakiTol: number;
    enforceSymmetry: boolean;
    maxCandidates: number;
    stats?: Record<string, number>;
    probeLineKey?: PruneLineKey;
  },
): { graph: GridCreaseGraph; removed: number } {
  let h = cloneGraph(g);
  let bestSc = globalScore(h, cornerIds, {
    maxDeg: opts.maxDeg,
    minCornerLines: opts.minCornerLines,
    kawasakiTol: opts.kawasakiTol,
  });
  let bestCk = priorityCornerKawasakiScore(h, cornerIds, {
    tol: opts.kawasakiTol,
  });

  const candidates = h.edgePairs().filter((e) => !h.isBoundaryEdge(e[0], e[1]));
  const lineGroups = new Map<string, number>();
  let unknownLineKeyTotal = 0;
  for (const e of candidates) {
    const lk = edgeLineKey(h, e);
    if (lk === null) {
      unknownLineKeyTotal += 1;
      continue;
    }
    const hash = lineKeyHash(lk);
    lineGroups.set(hash, (lineGroups.get(hash) ?? 0) + 1);
  }

  if (opts.stats) {
    opts.stats.prune_unknown_line_key_total =
      (opts.stats.prune_unknown_line_key_total ?? 0) + unknownLineKeyTotal;
    opts.stats.prune_line_groups_total =
      (opts.stats.prune_line_groups_total ?? 0) + lineGroups.size;
    if (
      opts.probeLineKey &&
      lineGroups.has(lineKeyHash(opts.probeLineKey))
    ) {
      opts.stats.prune_probe_line_present = (opts.stats.prune_probe_line_present ?? 0) + 1;
    }
  }

  const targeted = collectAxisCycleTargets(h, opts.maxCandidates);
  if (opts.stats) {
    opts.stats.prune_targeted_edges_total =
      (opts.stats.prune_targeted_edges_total ?? 0) + targeted.length;
    if (
      opts.probeLineKey &&
      targeted.some((t) => lineKeyEq(t.lineKey, opts.probeLineKey!))
    ) {
      opts.stats.prune_probe_line_targeted = (opts.stats.prune_probe_line_targeted ?? 0) + 1;
    }
  }

  let removedTotal = 0;
  const triedAxis = new Set<string>();
  for (const t of targeted.slice(0, opts.maxCandidates)) {
    const lkHash = lineKeyHash(t.lineKey);
    if (triedAxis.has(lkHash)) {
      continue;
    }
    triedAxis.add(lkHash);

    const isProbe = opts.probeLineKey ? lineKeyEq(t.lineKey, opts.probeLineKey) : false;
    if (opts.stats) {
      opts.stats.prune_tx_attempted_total = (opts.stats.prune_tx_attempted_total ?? 0) + 1;
      if (isProbe) {
        opts.stats.prune_probe_line_attempted =
          (opts.stats.prune_probe_line_attempted ?? 0) + 1;
      }
    }

    const tx = runDeleteGroupTransaction(h, t.deleteGroup, cornerIds, {
      enforceSymmetry: opts.enforceSymmetry,
      kawasakiTol: opts.kawasakiTol,
      baselineKBad: bestSc[0],
    });
    if (tx === null) {
      if (opts.stats) {
        opts.stats.prune_tx_fail_total = (opts.stats.prune_tx_fail_total ?? 0) + 1;
        if (isProbe) {
          opts.stats.prune_probe_line_fail_tx =
            (opts.stats.prune_probe_line_fail_tx ?? 0) + 1;
        }
      }
      continue;
    }
    if (tx.removed <= 0) {
      continue;
    }

    const sc = globalScore(tx.graph, cornerIds, {
      maxDeg: opts.maxDeg,
      minCornerLines: opts.minCornerLines,
      kawasakiTol: opts.kawasakiTol,
    });
    const ck = priorityCornerKawasakiScore(tx.graph, cornerIds, {
      tol: opts.kawasakiTol,
    });
    const scoreNonworse = compareNumericTuple(sc, bestSc) <= 0;
    const ckNonworse =
      ck[0] < bestCk[0] ||
      (ck[0] === bestCk[0] && ck[1] <= bestCk[1] + 1e-12);

    if (scoreNonworse && ckNonworse) {
      h = tx.graph;
      bestSc = sc;
      bestCk = ck;
      removedTotal += tx.removed;
      if (opts.stats) {
        opts.stats.prune_tx_accepted_total = (opts.stats.prune_tx_accepted_total ?? 0) + 1;
        if (isProbe) {
          opts.stats.prune_probe_line_accepted =
            (opts.stats.prune_probe_line_accepted ?? 0) + 1;
        }
      }
    } else if (opts.stats) {
      opts.stats.prune_tx_reject_score_total =
        (opts.stats.prune_tx_reject_score_total ?? 0) + 1;
      if (isProbe) {
        opts.stats.prune_probe_line_reject_score =
          (opts.stats.prune_probe_line_reject_score ?? 0) + 1;
      }
    }
  }

  return {
    graph: h,
    removed: removedTotal,
  };
}
