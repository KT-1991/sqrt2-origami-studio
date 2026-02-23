import { GridCreaseGraph } from "./creasegen_graph";
import { PAPER_MAX_F, PAPER_MIN_F } from "./paper_frame";

const TWO_PI = 2.0 * Math.PI;

export function normAngle(a: number): number {
  let x = a % TWO_PI;
  if (x < 0) {
    x += TWO_PI;
  }
  return x;
}

export function incidentAngles(
  g: GridCreaseGraph,
  vIdx: number,
  includeBoundary = false,
): number[] {
  const [vx, vy] = g.pointsF[vIdx];
  const out: number[] = [];
  for (const u of g.adj.get(vIdx) ?? []) {
    if (!includeBoundary && g.isBoundaryEdge(vIdx, u)) {
      continue;
    }
    const [ux, uy] = g.pointsF[u];
    const a = normAngle(Math.atan2(uy - vy, ux - vx));
    out.push(a);
  }
  out.sort((a, b) => a - b);
  return out;
}

export function uniqueAngles(angles: readonly number[], tol = 1e-10): number[] {
  if (angles.length === 0) {
    return [];
  }
  const arr = [...angles].sort((a, b) => a - b);
  const out = [arr[0]];
  for (let i = 1; i < arr.length; i += 1) {
    if (Math.abs(arr[i] - out[out.length - 1]) > tol) {
      out.push(arr[i]);
    }
  }
  if (out.length >= 2 && Math.abs(out[0] + TWO_PI - out[out.length - 1]) <= tol) {
    out.pop();
  }
  return out;
}

export function interiorWedge(
  px: number,
  py: number,
  eps = 1e-12,
): [number, number] {
  const onL = Math.abs(px - PAPER_MIN_F) <= eps;
  const onR = Math.abs(px - PAPER_MAX_F) <= eps;
  const onB = Math.abs(py - PAPER_MIN_F) <= eps;
  const onT = Math.abs(py - PAPER_MAX_F) <= eps;

  if (onL && onB) {
    return [0.0, Math.PI / 2.0];
  }
  if (onR && onB) {
    return [Math.PI / 2.0, Math.PI / 2.0];
  }
  if (onR && onT) {
    return [Math.PI, Math.PI / 2.0];
  }
  if (onL && onT) {
    return [(3.0 * Math.PI) / 2.0, Math.PI / 2.0];
  }
  if (onB) {
    return [0.0, Math.PI];
  }
  if (onT) {
    return [Math.PI, Math.PI];
  }
  if (onL) {
    return [(3.0 * Math.PI) / 2.0, Math.PI];
  }
  if (onR) {
    return [Math.PI / 2.0, Math.PI];
  }
  return [0.0, TWO_PI];
}

export function cornerSectors(g: GridCreaseGraph, vIdx: number): number[] {
  const [px, py] = g.pointsF[vIdx];
  const [start, width] = interiorWedge(px, py);
  const angs = uniqueAngles(incidentAngles(g, vIdx, false));
  let ts: number[] = [0.0, width];
  for (const a of angs) {
    const t = normAngle(a - start);
    if (-1e-12 <= t && t <= width + 1e-12) {
      ts.push(Math.min(Math.max(t, 0.0), width));
    }
  }
  ts = uniqueAngles(ts.sort((a, b) => a - b));
  if (ts.length <= 1) {
    return [];
  }
  const out: number[] = [];
  if (width >= TWO_PI - 1e-10) {
    for (let i = 0; i < ts.length; i += 1) {
      let d = ts[(i + 1) % ts.length] - ts[i];
      if (d <= 0.0) {
        d += TWO_PI;
      }
      out.push(d);
    }
    return out;
  }
  for (let i = 0; i < ts.length - 1; i += 1) {
    out.push(ts[i + 1] - ts[i]);
  }
  return out;
}

export function cornerConditionError(
  g: GridCreaseGraph,
  vIdx: number,
  maxDeg: number,
): number {
  const thr = (maxDeg * Math.PI) / 180.0;
  return cornerSectors(g, vIdx).reduce((acc, s) => acc + Math.max(0.0, s - thr), 0.0);
}

export function cornerLineCount(g: GridCreaseGraph, vIdx: number): number {
  let cnt = 0;
  for (const u of g.adj.get(vIdx) ?? []) {
    if (!g.isBoundaryEdge(vIdx, u)) {
      cnt += 1;
    }
  }
  return cnt;
}

export function requiredCornerLines(
  g: GridCreaseGraph,
  vIdx: number,
  opts: {
    maxDeg: number;
    minCornerLines?: number;
  },
): number {
  const maxDeg = opts.maxDeg;
  if (maxDeg <= 0.0) {
    throw new Error("maxDeg must be positive");
  }
  const minCornerLines = opts.minCornerLines ?? 2;
  const [px, py] = g.pointsF[vIdx];
  const [, width] = interiorWedge(px, py);
  const thr = (maxDeg * Math.PI) / 180.0;
  const needSectors = Math.max(1, Math.ceil((width - 1e-12) / thr));
  const needLines = width >= TWO_PI - 1e-10 ? needSectors : Math.max(0, needSectors - 1);
  return Math.max(minCornerLines, needLines);
}

export function cornerScore(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    maxDeg: number;
    minCornerLines?: number;
  },
): [number, number, number, number] {
  const minCornerLines = opts.minCornerLines ?? 2;
  const errs = cornerIds.map((v) => cornerConditionError(g, v, opts.maxDeg));
  const bad = errs.filter((e) => e > 1e-12).length;
  let lowdeg = 0;
  let lowdegPen = 0.0;
  for (const v of cornerIds) {
    const needLines = requiredCornerLines(g, v, {
      maxDeg: opts.maxDeg,
      minCornerLines,
    });
    const deficit = Math.max(0, needLines - cornerLineCount(g, v));
    if (deficit > 0) {
      lowdeg += 1;
      lowdegPen += deficit;
    }
  }
  const totalErr = errs.reduce((acc, e) => acc + e, 0.0);
  return [bad, lowdeg, totalErr, lowdegPen];
}
