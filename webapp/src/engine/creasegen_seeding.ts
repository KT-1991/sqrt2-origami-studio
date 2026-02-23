import { crossesExistingEdges, isPointOnLine } from "./creasegen_geometry";
import { GridCreaseGraph } from "./creasegen_graph";
import { adoptGraphState, cloneGraph } from "./creasegen_graph_ops";
import { diagonalSymmetryOk, isSquareCornerVertex } from "./creasegen_predicates";
import { ANGLE_COUNT, DIRS, ZERO, add, mul, q2Cmp, q2Sign, sub } from "./qsqrt2";

function edgePairKey(i: number, j: number): string {
  const a = i < j ? i : j;
  const b = i < j ? j : i;
  return `${a},${b}`;
}

export function exactDirIdxFromDelta(
  dx: ReturnType<typeof sub>,
  dy: ReturnType<typeof sub>,
): number | null {
  for (let k = 0; k < DIRS.length; k += 1) {
    const [rx, ry] = DIRS[k];
    const c = sub(mul(dx, ry), mul(dy, rx));
    if (q2Cmp(c, ZERO) !== 0) {
      continue;
    }
    const d = add(mul(dx, rx), mul(dy, ry));
    const s = q2Sign(d);
    if (s > 0) {
      return k;
    }
    if (s < 0) {
      return (k + ANGLE_COUNT / 2) % ANGLE_COUNT;
    }
  }
  return null;
}

export function isAlignedWith16Dirs(
  p: GridCreaseGraph["points"][number],
  q: GridCreaseGraph["points"][number],
): boolean {
  const dx = sub(q.x, p.x);
  const dy = sub(q.y, p.y);
  if (q2Cmp(dx, ZERO) === 0 && q2Cmp(dy, ZERO) === 0) {
    return false;
  }
  for (const [rx, ry] of DIRS) {
    if (q2Cmp(sub(mul(dx, ry), mul(dy, rx)), ZERO) === 0) {
      return true;
    }
  }
  return false;
}

export function addSegmentWithSplitsIds(
  g: GridCreaseGraph,
  startV: number,
  goalV: number,
  opts?: {
    maxSteps?: number;
    stats?: Record<string, number>;
  },
): boolean {
  if (startV === goalV) {
    return false;
  }
  const p0 = g.points[startV];
  const p1 = g.points[goalV];
  const d0 = exactDirIdxFromDelta(sub(p1.x, p0.x), sub(p1.y, p0.y));
  if (d0 === null) {
    return false;
  }
  const maxSteps = opts?.maxSteps ?? 32;
  const a = g.pointsF[startV];
  const b = g.pointsF[goalV];
  let changed = false;
  let cur = startV;
  const seen = new Set<number>([cur]);

  for (let step = 0; step < maxSteps; step += 1) {
    if (cur === goalV) {
      return changed;
    }
    if (g.hasEdge(cur, goalV)) {
      return true;
    }
    if (!crossesExistingEdges(g, cur, goalV)) {
      g.addEdge(cur, goalV, false);
      if (g.hasEdge(cur, goalV)) {
        return true;
      }
    }
    const hit = g.shootRayAndSplit(cur, d0, null, opts?.stats);
    if (hit === null) {
      return false;
    }
    const nxt = hit[1];
    if (nxt === cur) {
      return false;
    }
    if (!isPointOnLine(a, b, g.pointsF[nxt], 1e-7)) {
      return false;
    }
    changed = true;
    cur = nxt;
    if (seen.has(cur)) {
      return false;
    }
    seen.add(cur);
  }
  return false;
}

function dist2(a: [number, number], b: [number, number]): number {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

function mirroredEdgeKey(
  g: GridCreaseGraph,
  u: number,
  v: number,
): [string, [number, number] | null] {
  const mu = g.mirrorVertexIdx(u);
  const mv = g.mirrorVertexIdx(v);
  if (mu === null || mv === null) {
    return [edgePairKey(u, v), null];
  }
  return [edgePairKey(mu, mv), [mu, mv]];
}

export function seedDirectCornerConnections(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines: number;
    enforceSymmetry: boolean;
    stats?: Record<string, number>;
  },
): void {
  void opts.maxDeg;
  void opts.minCornerLines;

  const ids = [...cornerIds];
  const pairs: Array<[number, number, number]> = [];
  for (let i = 0; i < ids.length; i += 1) {
    for (let j = i + 1; j < ids.length; j += 1) {
      const u = ids[i];
      const v = ids[j];
      if (!isAlignedWith16Dirs(g.points[u], g.points[v])) {
        continue;
      }
      pairs.push([dist2(g.pointsF[u], g.pointsF[v]), u, v]);
    }
  }
  pairs.sort((lhs, rhs) => lhs[0] - rhs[0]);

  const attemptedSymKeys = new Set<string>();
  for (const [, u, v] of pairs) {
    if (isSquareCornerVertex(g, u) || isSquareCornerVertex(g, v)) {
      continue;
    }
    const e = edgePairKey(u, v);
    if (g.hasEdge(u, v)) {
      continue;
    }
    let mirrorEdge = e;
    let mirrorPair: [number, number] | null = [u, v];
    if (opts.enforceSymmetry) {
      const [mk, mp] = mirroredEdgeKey(g, u, v);
      if (mp === null) {
        continue;
      }
      mirrorEdge = mk;
      mirrorPair = mp;
      const skey = e <= mirrorEdge ? `${e}|${mirrorEdge}` : `${mirrorEdge}|${e}`;
      if (attemptedSymKeys.has(skey)) {
        continue;
      }
      attemptedSymKeys.add(skey);
    }

    opts.stats = opts.stats ?? {};
    opts.stats.seed_pair_attempt = (opts.stats.seed_pair_attempt ?? 0) + 1;
    const trial = cloneGraph(g);
    let ok = addSegmentWithSplitsIds(trial, u, v, {
      maxSteps: 64,
      stats: opts.stats,
    });
    if (ok && opts.enforceSymmetry && mirrorPair && mirrorEdge !== e) {
      ok = addSegmentWithSplitsIds(trial, mirrorPair[0], mirrorPair[1], {
        maxSteps: 64,
        stats: opts.stats,
      });
    }
    if (!ok) {
      opts.stats.seed_pair_failed = (opts.stats.seed_pair_failed ?? 0) + 1;
      continue;
    }
    if (opts.enforceSymmetry && !diagonalSymmetryOk(trial)) {
      opts.stats.seed_pair_sym_reject = (opts.stats.seed_pair_sym_reject ?? 0) + 1;
      continue;
    }
    adoptGraphState(g, trial);
    opts.stats.seed_pair_applied = (opts.stats.seed_pair_applied ?? 0) + 1;
  }
}
