import type { PointE, Qsqrt2 } from "./types";
import type { Q2Int } from "./qsqrt2";
import {
  ANGLE_COUNT,
  DIRS,
  DIRS_F,
  ONE,
  ZERO,
  add,
  div,
  mul,
  pointEApprox,
  q2Cmp,
  q2CmpInt,
  q2CrossInt,
  q2DivIntToQsqrt2,
  q2NegInt,
  q2SignAligned,
  q2SubInt,
  qsqrt2,
  sub,
  toQ2Int,
} from "./qsqrt2";
import { PAPER_MAX_Q, PAPER_MIN_Q } from "./paper_frame";
import { nearestDirIdx } from "./creasegen_direction";
import { collinearOverlapLength, raySegmentHitTFloat } from "./creasegen_geometry";
import { edgeHashPair, MASK64, pointKey, recordMissingPointStats } from "./creasegen_grid_utils";

const ZERO_I: Q2Int = { a: 0n, b: 0n, k: 0 };
const DIRS_I: Array<[Q2Int, Q2Int]> = DIRS.map(([dx, dy]) => [toQ2Int(dx), toQ2Int(dy)]);

function point(x: Qsqrt2, y: Qsqrt2): PointE {
  return { x, y };
}

function cross(ax: Qsqrt2, ay: Qsqrt2, bx: Qsqrt2, by: Qsqrt2): Qsqrt2 {
  return sub(mul(ax, by), mul(ay, bx));
}

export type RayHit = [number, number, number, PointE];

function raySegmentHitExact(
  origin: PointE,
  d: [Qsqrt2, Qsqrt2],
  a: PointE,
  b: PointE,
): [Qsqrt2, number, PointE] | null {
  const vx = sub(b.x, a.x);
  const vy = sub(b.y, a.y);
  const [dx, dy] = d;
  const denom = cross(dx, dy, vx, vy);
  if (q2Cmp(denom, ZERO) === 0) {
    return null;
  }
  const wx = sub(a.x, origin.x);
  const wy = sub(a.y, origin.y);
  const t = div(cross(wx, wy, vx, vy), denom);
  const u = div(cross(wx, wy, dx, dy), denom);
  if (q2Cmp(t, ZERO) <= 0) {
    return null;
  }
  if (q2Cmp(u, ZERO) < 0 || q2Cmp(u, ONE) > 0) {
    return null;
  }
  if (q2Cmp(u, ZERO) <= 0) {
    return [t, -1, a];
  }
  if (q2Cmp(u, ONE) >= 0) {
    return [t, 1, b];
  }
  return [t, 0, point(add(origin.x, mul(t, dx)), add(origin.y, mul(t, dy)))];
}

function raySegmentHit(
  origin: PointE,
  d: [Qsqrt2, Qsqrt2],
  a: PointE,
  b: PointE,
  originI?: [Q2Int, Q2Int] | null,
  dI?: [Q2Int, Q2Int] | null,
  aI?: [Q2Int, Q2Int] | null,
  bI?: [Q2Int, Q2Int] | null,
): [Qsqrt2, number, PointE] | null {
  const [ox, oy] = originI ?? [toQ2Int(origin.x), toQ2Int(origin.y)];
  const [ax, ay] = aI ?? [toQ2Int(a.x), toQ2Int(a.y)];
  const [bx, by] = bI ?? [toQ2Int(b.x), toQ2Int(b.y)];
  const [dx, dy] = dI ?? [toQ2Int(d[0]), toQ2Int(d[1])];

  const vx = q2SubInt(bx, ax);
  const vy = q2SubInt(by, ay);
  const wx = q2SubInt(ax, ox);
  const wy = q2SubInt(ay, oy);

  let denom = q2CrossInt(dx, dy, vx, vy);
  const sden = q2SignAligned(denom.a, denom.b);
  if (sden === 0) {
    return null;
  }

  let tNum = q2CrossInt(wx, wy, vx, vy);
  const stn = q2SignAligned(tNum.a, tNum.b);
  if (stn === 0 || stn !== sden) {
    return null;
  }

  let uNum = q2CrossInt(wx, wy, dx, dy);
  if (sden < 0) {
    denom = q2NegInt(denom);
    tNum = q2NegInt(tNum);
    uNum = q2NegInt(uNum);
  }

  if (q2CmpInt(uNum, ZERO_I) < 0 || q2CmpInt(uNum, denom) > 0) {
    return null;
  }

  const t = q2DivIntToQsqrt2(tNum, denom);
  if (q2CmpInt(uNum, ZERO_I) === 0) {
    return [t, -1, a];
  }
  if (q2CmpInt(uNum, denom) === 0) {
    return [t, 1, b];
  }
  return [t, 0, point(add(origin.x, mul(t, d[0])), add(origin.y, mul(t, d[1])))];
}

export interface EnumeratedGrid {
  points: PointE[];
  p2i: Map<string, number>;
}

function qsqrt2Key(z: Qsqrt2): string {
  return `${z.a},${z.b},${z.k}`;
}

export function enumerateGridPoints(
  aMax: number,
  bMax: number,
  kMax: number,
): EnumeratedGrid {
  const xvals = new Map<string, Qsqrt2>();
  for (let k = 0; k <= kMax; k += 1) {
    for (let a = -aMax; a <= aMax; a += 1) {
      for (let b = -bMax; b <= bMax; b += 1) {
        const z = qsqrt2(BigInt(a), BigInt(b), k);
        if (q2Cmp(z, PAPER_MIN_Q) >= 0 && q2Cmp(z, PAPER_MAX_Q) <= 0) {
          xvals.set(qsqrt2Key(z), z);
        }
      }
    }
  }

  const xs = [...xvals.values()];
  const points: PointE[] = [];
  const p2i = new Map<string, number>();
  for (const x of xs) {
    for (const y of xs) {
      const p = point(x, y);
      const idx = points.length;
      points.push(p);
      p2i.set(pointKey(p), idx);
    }
  }
  return { points, p2i };
}

interface EdgeRecord {
  i: number;
  j: number;
  boundary: boolean;
  birth: number;
  dirBucket: number | null;
}

type TxOp =
  | { op: "SET_EDGE_BIRTH_COUNTER"; edgeBirthCounter: number }
  | { op: "DEACTIVATE_VERTEX"; v: number }
  | { op: "SET_BOUNDARY_FLAG"; key: string; prev: boolean }
  | { op: "REMOVE_EDGE_RAW"; i: number; j: number }
  | { op: "RESTORE_EDGE_RAW"; i: number; j: number; boundary: boolean; birth: number | null };

export interface GridCreaseGraphArgs {
  points: ReadonlyArray<PointE>;
  p2i: ReadonlyMap<string, number>;
  pointsF?: ReadonlyArray<[number, number]>;
  shareBase?: boolean;
  useLocalRayDirty?: boolean;
}

export class GridCreaseGraph {
  readonly points: PointE[];
  readonly pointToId: Map<string, number>;
  readonly pointsF: Array<[number, number]>;

  activeVertices = new Set<number>();
  edges = new Set<string>();
  boundaryEdges = new Set<string>();
  edgeBirth = new Map<string, number>();
  edgeBirthCounter = 0;
  adj = new Map<number, Set<number>>();
  rayNext = new Map<number, Array<number | null>>();
  rayHit = new Map<number, Array<RayHit | null>>();
  rayHitRev = new Map<string, Set<number>>();
  rayDirty = new Set<number>();
  edgeDirIdx = new Map<string, number | null>();
  edgeParallelBuckets: Array<Set<string>> = Array.from(
    { length: ANGLE_COUNT / 2 },
    () => new Set<string>(),
  );
  edgeUnknownDir = new Set<string>();
  edgeScanCacheVersion = -1;
  edgeScanCache = new Map<number, Array<[number, number]>>();
  incidentDirsCache = new Map<number, number[]>();
  incidentDirsDirty = new Set<number>();
  kawasakiCache = new Map<number, number>();
  kawasakiDirty = new Set<number>();
  pointIntCache = new Map<number, [Q2Int, Q2Int] | null>();
  mirrorVidCache = new Map<number, number | null>();
  stateHash1 = 0n;
  stateHash2 = 0n;
  useLocalRayDirty: boolean;
  txLogs: TxOp[][] = [];
  txReplaying = false;
  edgeVersion = 0;

  private edgeRecords = new Map<string, EdgeRecord>();

  constructor(args: GridCreaseGraphArgs) {
    const shareBase = Boolean(args.shareBase);
    if (shareBase) {
      this.points = args.points as PointE[];
      this.pointToId = args.p2i as Map<string, number>;
      this.pointsF = args.pointsF
        ? (args.pointsF as Array<[number, number]>)
        : this.points.map((p) => pointEApprox(p));
    } else {
      this.points = [...args.points];
      this.pointToId = new Map(args.p2i);
      this.pointsF = args.pointsF ? [...args.pointsF] : this.points.map((p) => pointEApprox(p));
    }
    this.useLocalRayDirty = Boolean(args.useLocalRayDirty);
  }

  private normEdge(i: number, j: number): [number, number] {
    return i < j ? [i, j] : [j, i];
  }

  private edgeKey(i: number, j: number): string {
    const [a, b] = this.normEdge(i, j);
    return `${a},${b}`;
  }

  private pairFromKey(key: string): [number, number] {
    const idx = key.indexOf(",");
    const a = Number(key.slice(0, idx));
    const b = Number(key.slice(idx + 1));
    return [a, b];
  }

  private toggleEdgeHash(i: number, j: number): void {
    const [h1, h2] = edgeHashPair(i, j);
    this.stateHash1 = (this.stateHash1 ^ h1) & MASK64;
    this.stateHash2 = (this.stateHash2 ^ h2) & MASK64;
  }

  private txRecord(op: TxOp): void {
    if (this.txLogs.length > 0 && !this.txReplaying) {
      this.txLogs[this.txLogs.length - 1].push(op);
    }
  }

  txBegin(): void {
    this.txLogs.push([{ op: "SET_EDGE_BIRTH_COUNTER", edgeBirthCounter: this.edgeBirthCounter }]);
  }

  private deactivateVertexShallow(v: number): void {
    if (!this.activeVertices.has(v)) {
      return;
    }
    const neigh = this.adj.get(v);
    if (neigh) {
      for (const u of [...neigh]) {
        this.adj.get(u)?.delete(v);
      }
    }
    this.clearRayHitRow(v);
    this.activeVertices.delete(v);
    this.adj.delete(v);
    this.rayNext.delete(v);
    this.rayHit.delete(v);
    this.rayDirty.delete(v);
    this.incidentDirsCache.delete(v);
    this.incidentDirsDirty.delete(v);
    this.kawasakiCache.delete(v);
    this.kawasakiDirty.delete(v);
  }

  private addEdgeRaw(
    i: number,
    j: number,
    boundary: boolean,
    birth: number | null,
    invalidateFace = true,
  ): void {
    if (i === j) {
      return;
    }
    this.activateVertex(i);
    this.activateVertex(j);
    const [a, b] = this.normEdge(i, j);
    const key = this.edgeKey(a, b);
    const existing = this.edgeRecords.get(key);
    if (existing) {
      if (boundary) {
        existing.boundary = true;
        this.boundaryEdges.add(key);
      }
      return;
    }

    this.edges.add(key);
    this.toggleEdgeHash(a, b);

    const birthOrder = birth === null ? this.edgeBirthCounter : birth;
    this.edgeBirth.set(key, birthOrder);
    if (birth === null) {
      this.edgeBirthCounter += 1;
    }

    if (boundary) {
      this.boundaryEdges.add(key);
    }
    this.adj.get(a)?.add(b);
    this.adj.get(b)?.add(a);
    const bucket = this.edgeDirBucket(a, b);
    this.edgeDirIdx.set(key, bucket);
    if (bucket === null) {
      this.edgeUnknownDir.add(key);
    } else {
      this.edgeParallelBuckets[bucket].add(key);
    }
    this.edgeRecords.set(key, {
      i: a,
      j: b,
      boundary,
      birth: birthOrder,
      dirBucket: bucket,
    });
    this.markLocalDirty(a);
    this.markLocalDirty(b);
    this.edgeVersion += 1;
    if (invalidateFace) {
      this.invalidateFaceCache();
    }
  }

  private removeEdgeRaw(i: number, j: number, invalidateFace = true): void {
    const [a, b] = this.normEdge(i, j);
    const key = this.edgeKey(a, b);
    const rec = this.edgeRecords.get(key);
    if (!rec) {
      return;
    }
    this.toggleEdgeHash(a, b);
    this.edges.delete(key);
    this.boundaryEdges.delete(key);
    this.edgeBirth.delete(key);
    this.adj.get(a)?.delete(b);
    this.adj.get(b)?.delete(a);
    const bucket = this.edgeDirIdx.get(key) ?? null;
    this.edgeDirIdx.delete(key);
    if (bucket === null) {
      this.edgeUnknownDir.delete(key);
    } else {
      this.edgeParallelBuckets[bucket].delete(key);
    }
    this.edgeRecords.delete(key);
    this.markLocalDirty(a);
    this.markLocalDirty(b);
    this.edgeVersion += 1;
    if (invalidateFace) {
      this.invalidateFaceCache();
    }
  }

  txRollback(): void {
    if (this.txLogs.length === 0) {
      return;
    }
    const log = this.txLogs.pop();
    if (!log) {
      return;
    }
    this.txReplaying = true;
    try {
      for (let i = log.length - 1; i >= 0; i -= 1) {
        const op = log[i];
        if (op.op === "SET_EDGE_BIRTH_COUNTER") {
          this.edgeBirthCounter = op.edgeBirthCounter;
          continue;
        }
        if (op.op === "DEACTIVATE_VERTEX") {
          this.deactivateVertexShallow(op.v);
          continue;
        }
        if (op.op === "SET_BOUNDARY_FLAG") {
          const rec = this.edgeRecords.get(op.key);
          if (!rec) {
            continue;
          }
          rec.boundary = op.prev;
          if (op.prev) {
            this.boundaryEdges.add(op.key);
          } else {
            this.boundaryEdges.delete(op.key);
          }
          continue;
        }
        if (op.op === "REMOVE_EDGE_RAW") {
          this.removeEdgeRaw(op.i, op.j);
          continue;
        }
        this.addEdgeRaw(op.i, op.j, op.boundary, op.birth);
      }
    } finally {
      this.txReplaying = false;
    }
  }

  txCommit(): void {
    if (this.txLogs.length > 0) {
      this.txLogs.pop();
    }
  }

  activateVertex(v: number): void {
    if (!this.activeVertices.has(v)) {
      this.txRecord({ op: "DEACTIVATE_VERTEX", v });
    }
    this.activeVertices.add(v);
    if (!this.adj.has(v)) {
      this.adj.set(v, new Set<number>());
    }
    if (!this.rayNext.has(v)) {
      this.rayNext.set(v, Array.from({ length: ANGLE_COUNT }, () => null));
    }
    if (!this.rayHit.has(v)) {
      this.rayHit.set(v, Array.from({ length: ANGLE_COUNT }, () => null));
    }
    this.rayDirty.add(v);
    this.incidentDirsDirty.add(v);
    this.kawasakiDirty.add(v);
  }

  private markLocalDirty(v: number): void {
    this.incidentDirsDirty.add(v);
    this.kawasakiDirty.add(v);
  }

  private invalidateFaceCache(): void {
    return;
  }

  private clearRayHitRow(v: number): void {
    const row = this.rayHit.get(v);
    if (!row) {
      return;
    }
    for (const hit of row) {
      if (!hit) {
        continue;
      }
      const key = this.edgeKey(hit[0], hit[1]);
      const vs = this.rayHitRev.get(key);
      if (!vs) {
        continue;
      }
      vs.delete(v);
      if (vs.size === 0) {
        this.rayHitRev.delete(key);
      }
    }
  }

  private pointIntPair(v: number): [Q2Int, Q2Int] | null {
    if (this.pointIntCache.has(v)) {
      return this.pointIntCache.get(v) ?? null;
    }
    const p = this.points[v];
    const out: [Q2Int, Q2Int] = [toQ2Int(p.x), toQ2Int(p.y)];
    this.pointIntCache.set(v, out);
    return out;
  }

  mirrorVertexIdx(v: number): number | null {
    if (this.mirrorVidCache.has(v)) {
      return this.mirrorVidCache.get(v) ?? null;
    }
    const p = this.points[v];
    const key = `${p.y.a},${p.y.b},${p.y.k},${p.x.a},${p.x.b},${p.x.k}`;
    const mv = this.pointToId.get(key) ?? null;
    this.mirrorVidCache.set(v, mv);
    return mv;
  }

  private edgeDirBucket(i: number, j: number): number | null {
    const [x1, y1] = this.pointsF[i];
    const [x2, y2] = this.pointsF[j];
    if (Math.abs(x2 - x1) + Math.abs(y2 - y1) <= 1e-15) {
      return null;
    }
    const d = nearestDirIdx(x2 - x1, y2 - y1);
    return d % (ANGLE_COUNT / 2);
  }

  private edgeCandidatesForDir(dirIdx: number): Array<[number, number]> {
    if (this.edgeScanCacheVersion !== this.edgeVersion) {
      this.edgeScanCache.clear();
      this.edgeScanCacheVersion = this.edgeVersion;
    }
    const cached = this.edgeScanCache.get(dirIdx);
    if (cached) {
      return cached;
    }
    const blocked = dirIdx % (ANGLE_COUNT / 2);
    const cands: Array<[number, number]> = [];
    for (let b = 0; b < this.edgeParallelBuckets.length; b += 1) {
      if (b === blocked) {
        continue;
      }
      for (const key of this.edgeParallelBuckets[b]) {
        const rec = this.edgeRecords.get(key);
        if (!rec) {
          continue;
        }
        cands.push([rec.i, rec.j]);
      }
    }
    for (const key of this.edgeUnknownDir) {
      const rec = this.edgeRecords.get(key);
      if (!rec) {
        continue;
      }
      cands.push([rec.i, rec.j]);
    }
    this.edgeScanCache.set(dirIdx, cands);
    return cands;
  }

  private iterEdgesForRayDir(dirIdx: number): Array<[number, number]> {
    return this.edgeCandidatesForDir(dirIdx);
  }

  *iterEdges(): Iterable<[number, number]> {
    for (const rec of this.edgeRecords.values()) {
      yield [rec.i, rec.j];
    }
  }

  addVertex(p: PointE): number {
    const key = pointKey(p);
    const v = this.pointToId.get(key);
    if (v === undefined) {
      throw new Error(`point not found in pre-enumerated grid: ${pointEApprox(p).join(",")}`);
    }
    this.activateVertex(v);
    return v;
  }

  addEdge(
    i: number,
    j: number,
    boundary = false,
    markRayDirty = true,
    invalidateFace = true,
  ): void {
    if (i === j) {
      return;
    }
    this.activateVertex(i);
    this.activateVertex(j);
    const [a, b] = this.normEdge(i, j);
    const key = this.edgeKey(a, b);
    const existing = this.edgeRecords.get(key);
    if (existing) {
      if (boundary && !existing.boundary) {
        this.txRecord({ op: "SET_BOUNDARY_FLAG", key, prev: false });
        existing.boundary = true;
        this.boundaryEdges.add(key);
      }
      return;
    }

    const pi = this.pointsF[i];
    const pj = this.pointsF[j];
    const bucket = this.edgeDirBucket(i, j);
    if (bucket === null) {
      for (const rec of this.edgeRecords.values()) {
        const pu = this.pointsF[rec.i];
        const pv = this.pointsF[rec.j];
        if (collinearOverlapLength(pi, pj, pu, pv) > 1e-10) {
          return;
        }
      }
    } else {
      for (const eKey of this.edgeParallelBuckets[bucket]) {
        const rec = this.edgeRecords.get(eKey);
        if (!rec) {
          continue;
        }
        const pu = this.pointsF[rec.i];
        const pv = this.pointsF[rec.j];
        if (collinearOverlapLength(pi, pj, pu, pv) > 1e-10) {
          return;
        }
      }
      for (const eKey of this.edgeUnknownDir) {
        const rec = this.edgeRecords.get(eKey);
        if (!rec) {
          continue;
        }
        const pu = this.pointsF[rec.i];
        const pv = this.pointsF[rec.j];
        if (collinearOverlapLength(pi, pj, pu, pv) > 1e-10) {
          return;
        }
      }
    }

    this.txRecord({ op: "REMOVE_EDGE_RAW", i: a, j: b });
    this.addEdgeRaw(i, j, boundary, null, invalidateFace);
    if (markRayDirty) {
      this.markRayDirtyAfterChange([[a, b]]);
    }
  }

  removeEdge(i: number, j: number, markRayDirty = true, invalidateFace = true): void {
    const [a, b] = this.normEdge(i, j);
    const key = this.edgeKey(a, b);
    const rec = this.edgeRecords.get(key);
    if (!rec) {
      return;
    }
    const oldBirth = this.edgeBirth.get(key) ?? null;
    this.txRecord({
      op: "RESTORE_EDGE_RAW",
      i: a,
      j: b,
      boundary: rec.boundary,
      birth: oldBirth,
    });
    this.removeEdgeRaw(i, j, invalidateFace);
    if (markRayDirty) {
      this.markRayDirtyAfterChange([[a, b]]);
    }
  }

  initSquareBoundary(): [number, number, number, number] {
    const v0 = this.addVertex(point(PAPER_MIN_Q, PAPER_MIN_Q));
    const v1 = this.addVertex(point(PAPER_MAX_Q, PAPER_MIN_Q));
    const v2 = this.addVertex(point(PAPER_MAX_Q, PAPER_MAX_Q));
    const v3 = this.addVertex(point(PAPER_MIN_Q, PAPER_MAX_Q));
    this.addEdge(v0, v1, true);
    this.addEdge(v1, v2, true);
    this.addEdge(v2, v3, true);
    this.addEdge(v3, v0, true);
    return [v0, v1, v2, v3];
  }

  recomputeRayNextForVertex(v: number): void {
    this.activateVertex(v);
    const origin = this.points[v];
    const originI = this.pointIntPair(v);
    const originF = this.pointsF[v];
    const row: Array<number | null> = Array.from({ length: ANGLE_COUNT }, () => null);
    const rowHit: Array<RayHit | null> = Array.from({ length: ANGLE_COUNT }, () => null);
    const tol = 1e-9;

    for (let d = 0; d < ANGLE_COUNT; d += 1) {
      const dF = DIRS_F[d];
      const dI = DIRS_I[d];
      const [dxF, dyF] = dF;
      const originProj = originF[0] * dxF + originF[1] * dyF;
      let bestTF: number | null = null;
      let shortlist: Array<[number, number, number]> = [];

      for (const [i, j] of this.iterEdgesForRayDir(d)) {
        const pi = this.pointsF[i];
        const pj = this.pointsF[j];
        if (
          pi[0] * dxF + pi[1] * dyF <= originProj + 1e-12 &&
          pj[0] * dxF + pj[1] * dyF <= originProj + 1e-12
        ) {
          continue;
        }
        const tF = raySegmentHitTFloat(originF, dF, pi, pj, 1e-12);
        if (tF === null) {
          continue;
        }
        if (bestTF === null || tF < bestTF - tol) {
          bestTF = tF;
          shortlist = [[tF, i, j]];
        } else if (Math.abs(tF - bestTF) <= tol) {
          shortlist.push([tF, i, j]);
        }
      }

      if (shortlist.length === 0) {
        row[d] = null;
        rowHit[d] = null;
        continue;
      }

      let bestRowT: Qsqrt2 | null = null;
      let bestHitIdx: number | null = null;
      let bestT: Qsqrt2 | null = null;
      let bestHit: RayHit | null = null;
      if (shortlist.length > 1) {
        shortlist = shortlist.sort((lhs, rhs) => lhs[0] - rhs[0]);
      }
      for (const [, i, j] of shortlist) {
        const hit = raySegmentHit(
          origin,
          DIRS[d],
          this.points[i],
          this.points[j],
          originI,
          dI,
          this.pointIntPair(i),
          this.pointIntPair(j),
        );
        if (hit === null) {
          continue;
        }
        const [t, hitPos, p] = hit;
        if (bestT === null || q2Cmp(t, bestT) < 0) {
          bestT = t;
          bestHit = [i, j, hitPos, p];
        }
        let cand: number | null = null;
        if (hitPos < 0) {
          cand = i;
        } else if (hitPos > 0) {
          cand = j;
        } else {
          cand = this.pointToId.get(pointKey(p)) ?? null;
        }
        if (cand === null || cand === v) {
          continue;
        }
        if (bestRowT === null || q2Cmp(t, bestRowT) < 0) {
          bestRowT = t;
          bestHitIdx = cand;
        }
      }
      row[d] = bestHitIdx;
      rowHit[d] = bestHit;
    }

    this.rayNext.set(v, row);
    this.clearRayHitRow(v);
    this.rayHit.set(v, rowHit);
    for (const hit of rowHit) {
      if (!hit) {
        continue;
      }
      const key = this.edgeKey(hit[0], hit[1]);
      if (!this.rayHitRev.has(key)) {
        this.rayHitRev.set(key, new Set<number>());
      }
      this.rayHitRev.get(key)?.add(v);
    }
    this.rayDirty.delete(v);
  }

  private markAllRayDirty(): void {
    for (const v of this.activeVertices) {
      this.rayDirty.add(v);
    }
  }

  private markRayDirtyAfterChange(changedEdges: ReadonlyArray<[number, number]>): void {
    if (this.useLocalRayDirty) {
      this.markRayDirtyByChangedEdges(changedEdges);
    } else {
      this.markAllRayDirty();
    }
  }

  private markRayDirtyByChangedEdges(changedEdges: ReadonlyArray<[number, number]>): void {
    if (changedEdges.length === 0) {
      return;
    }
    const changed = new Set<string>();
    for (const [i, j] of changedEdges) {
      changed.add(this.edgeKey(i, j));
    }

    const localTouch = new Set<number>();
    const addedEdges: Array<[number, number]> = [];
    for (const key of changed) {
      const [i, j] = this.pairFromKey(key);
      localTouch.add(i);
      localTouch.add(j);
      for (const u of this.adj.get(i) ?? []) {
        localTouch.add(u);
      }
      for (const u of this.adj.get(j) ?? []) {
        localTouch.add(u);
      }
      if (this.edgeRecords.has(key)) {
        addedEdges.push([i, j]);
      }
    }
    for (const v of localTouch) {
      if (this.activeVertices.has(v)) {
        this.rayDirty.add(v);
      }
    }

    for (const key of changed) {
      for (const v of this.rayHitRev.get(key) ?? []) {
        this.rayDirty.add(v);
      }
    }

    if (addedEdges.length === 0) {
      return;
    }

    const edgeSegs: Array<[[number, number], [number, number]]> = addedEdges.map(([i, j]) => [
      this.pointsF[i],
      this.pointsF[j],
    ]);
    for (const v of this.activeVertices) {
      if (this.rayDirty.has(v)) {
        continue;
      }
      const originF = this.pointsF[v];
      let hitAny = false;
      for (const dF of DIRS_F) {
        for (const [aF, bF] of edgeSegs) {
          if (raySegmentHitTFloat(originF, dF, aF, bF, 1e-12) !== null) {
            this.rayDirty.add(v);
            hitAny = true;
            break;
          }
        }
        if (hitAny) {
          break;
        }
      }
    }
  }

  ensureRayNext(v: number): Array<number | null> {
    if (!this.activeVertices.has(v)) {
      this.activateVertex(v);
    }
    if (this.rayDirty.has(v)) {
      this.recomputeRayNextForVertex(v);
    }
    const row = this.rayNext.get(v);
    if (!row) {
      const out = Array.from({ length: ANGLE_COUNT }, () => null);
      this.rayNext.set(v, out);
      return out;
    }
    return row;
  }

  rayNextAt(v: number, dirIdx: number): number | null {
    return this.ensureRayNext(v)[dirIdx];
  }

  rayHitAt(v: number, dirIdx: number): RayHit | null {
    this.ensureRayNext(v);
    return this.rayHit.get(v)?.[dirIdx] ?? null;
  }

  recomputeRayNextAll(): void {
    const verts = [...this.activeVertices].sort((a, b) => a - b);
    for (const v of verts) {
      this.recomputeRayNextForVertex(v);
    }
  }

  private firstHitEdgeFromCandidates(
    originV: number,
    dirIdx: number,
    candidates: Iterable<[number, number]>,
  ): [Qsqrt2, number, number, number, PointE] | null {
    const originF = this.pointsF[originV];
    const dF = DIRS_F[dirIdx];
    const [dxF, dyF] = dF;
    const originProj = originF[0] * dxF + originF[1] * dyF;
    const dI = DIRS_I[dirIdx];
    const origin = this.points[originV];
    const originI = this.pointIntPair(originV);
    const tol = 1e-9;
    let bestTF: number | null = null;
    let shortlist: Array<[number, number, number]> = [];

    for (const [i, j] of candidates) {
      const pi = this.pointsF[i];
      const pj = this.pointsF[j];
      if (
        pi[0] * dxF + pi[1] * dyF <= originProj + 1e-12 &&
        pj[0] * dxF + pj[1] * dyF <= originProj + 1e-12
      ) {
        continue;
      }
      const tF = raySegmentHitTFloat(originF, dF, pi, pj, 1e-12);
      if (tF === null) {
        continue;
      }
      if (bestTF === null || tF < bestTF - tol) {
        bestTF = tF;
        shortlist = [[tF, i, j]];
      } else if (Math.abs(tF - bestTF) <= tol) {
        shortlist.push([tF, i, j]);
      }
    }

    if (shortlist.length === 0) {
      return null;
    }

    let bestT: Qsqrt2 | null = null;
    let best: [Qsqrt2, number, number, number, PointE] | null = null;
    if (shortlist.length > 1) {
      shortlist = shortlist.sort((lhs, rhs) => lhs[0] - rhs[0]);
    }
    for (const [, i, j] of shortlist) {
      const hit = raySegmentHit(
        origin,
        DIRS[dirIdx],
        this.points[i],
        this.points[j],
        originI,
        dI,
        this.pointIntPair(i),
        this.pointIntPair(j),
      );
      if (hit === null) {
        continue;
      }
      const [t, hitPos, p] = hit;
      if (bestT === null || q2Cmp(t, bestT) < 0) {
        bestT = t;
        best = [t, i, j, hitPos, p];
      }
    }
    return best;
  }

  private firstHitEdgeGlobal(
    originV: number,
    dirIdx: number,
  ): [Qsqrt2, number, number, number, PointE] | null {
    return this.firstHitEdgeFromCandidates(originV, dirIdx, this.iterEdgesForRayDir(dirIdx));
  }

  firstHitEdge(originV: number, dirIdx: number): RayHit | null {
    if (this.activeVertices.has(originV) && !this.rayDirty.has(originV)) {
      const row = this.rayHit.get(originV);
      if (row) {
        return row[dirIdx];
      }
    }
    const hit = this.firstHitEdgeGlobal(originV, dirIdx);
    if (hit === null) {
      return null;
    }
    const [, i, j, hitPos, p] = hit;
    return [i, j, hitPos, p];
  }

  shootRayAndSplit(
    originV: number,
    dirIdx: number,
    knownHit: RayHit | null = null,
    stats?: Record<string, number>,
  ): [number, number] | null {
    if (!this.activeVertices.has(originV)) {
      return null;
    }
    const hit = knownHit ?? this.firstHitEdge(originV, dirIdx);
    if (hit === null) {
      return null;
    }
    const [i, j, hitPos, p] = hit;
    const oldKey = this.edgeKey(i, j);
    const wasBoundary = this.boundaryEdges.has(oldKey);
    const changedEdges: Array<[number, number]> = [];
    const batchedFaceInvalidate = hitPos === 0;
    let hitV: number;
    if (hitPos < 0) {
      hitV = i;
    } else if (hitPos > 0) {
      hitV = j;
    } else {
      hitV = this.pointToId.get(pointKey(p)) ?? -1;
      if (hitV < 0) {
        recordMissingPointStats(stats, p);
        return null;
      }
      this.activateVertex(hitV);
      this.removeEdge(i, j, false, !batchedFaceInvalidate);
      changedEdges.push(this.normEdge(i, j));
      this.addEdge(i, hitV, wasBoundary, false, !batchedFaceInvalidate);
      this.addEdge(hitV, j, wasBoundary, false, !batchedFaceInvalidate);
      changedEdges.push(this.normEdge(i, hitV));
      changedEdges.push(this.normEdge(hitV, j));
    }
    this.addEdge(originV, hitV, false, false, !batchedFaceInvalidate);
    changedEdges.push(this.normEdge(originV, hitV));
    if (batchedFaceInvalidate) {
      this.invalidateFaceCache();
    }
    this.markRayDirtyAfterChange(changedEdges);
    return [originV, hitV];
  }

  edgePairs(): Array<[number, number]> {
    return [...this.edgeRecords.values()].map((rec) => [rec.i, rec.j]);
  }

  hasEdge(i: number, j: number): boolean {
    return this.edgeRecords.has(this.edgeKey(i, j));
  }

  isBoundaryEdge(i: number, j: number): boolean {
    return this.boundaryEdges.has(this.edgeKey(i, j));
  }

  boundaryEdgePairs(): Array<[number, number]> {
    return [...this.edgeRecords.values()]
      .filter((rec) => rec.boundary)
      .map((rec) => [rec.i, rec.j]);
  }

  edgeBirthOrder(i: number, j: number): number | undefined {
    return this.edgeBirth.get(this.edgeKey(i, j));
  }

  edgeDirBucketAt(i: number, j: number): number | null | undefined {
    return this.edgeDirIdx.get(this.edgeKey(i, j));
  }

  copyMutableStateFrom(src: GridCreaseGraph): void {
    this.activeVertices = new Set(src.activeVertices);
    this.edges = new Set(src.edges);
    this.boundaryEdges = new Set(src.boundaryEdges);
    this.edgeBirth = new Map(src.edgeBirth);
    this.edgeBirthCounter = src.edgeBirthCounter;
    this.adj = new Map([...src.adj.entries()].map(([k, vs]) => [k, new Set(vs)]));
    this.rayNext = new Map(src.rayNext);
    this.rayHit = new Map(src.rayHit);
    this.rayHitRev = new Map(
      [...src.rayHitRev.entries()].map(([key, vs]) => [key, new Set(vs)]),
    );
    this.rayDirty = new Set(src.rayDirty);
    this.edgeDirIdx = new Map(src.edgeDirIdx);
    this.edgeParallelBuckets = src.edgeParallelBuckets.map((es) => new Set(es));
    this.edgeUnknownDir = new Set(src.edgeUnknownDir);
    this.edgeScanCacheVersion = src.edgeScanCacheVersion;
    this.edgeScanCache = new Map(
      [...src.edgeScanCache.entries()].map(([k, edges]) => [k, [...edges]]),
    );
    this.incidentDirsCache = new Map(
      [...src.incidentDirsCache.entries()].map(([k, dirs]) => [k, [...dirs]]),
    );
    this.incidentDirsDirty = new Set(src.incidentDirsDirty);
    this.kawasakiCache = new Map(src.kawasakiCache);
    this.kawasakiDirty = new Set(src.kawasakiDirty);
    this.pointIntCache = new Map(src.pointIntCache);
    this.mirrorVidCache = new Map(src.mirrorVidCache);
    this.stateHash1 = src.stateHash1;
    this.stateHash2 = src.stateHash2;
    this.useLocalRayDirty = src.useLocalRayDirty;
    this.edgeVersion = src.edgeVersion;
    this.edgeRecords = new Map(
      [...src.edgeRecords.entries()].map(([key, rec]) => [key, { ...rec }]),
    );
  }

  cloneSharedBase(): GridCreaseGraph {
    const h = new GridCreaseGraph({
      points: this.points,
      p2i: this.pointToId,
      pointsF: this.pointsF,
      shareBase: true,
      useLocalRayDirty: this.useLocalRayDirty,
    });
    h.copyMutableStateFrom(this);
    return h;
  }

  stateKey(): [bigint, bigint, number] {
    return [this.stateHash1, this.stateHash2, this.edges.size];
  }
}
