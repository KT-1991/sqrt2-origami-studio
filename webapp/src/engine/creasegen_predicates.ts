import { pointKey } from "./creasegen_grid_utils";
import type { PointE } from "./types";
import { GridCreaseGraph } from "./creasegen_graph";
import { PAPER_MAX_F, PAPER_MIN_F } from "./paper_frame";

export function isBoundaryVertex(g: GridCreaseGraph, vIdx: number, tol = 1e-10): boolean {
  const [x, y] = g.pointsF[vIdx];
  return (
    Math.abs(x - PAPER_MIN_F) <= tol ||
    Math.abs(x - PAPER_MAX_F) <= tol ||
    Math.abs(y - PAPER_MIN_F) <= tol ||
    Math.abs(y - PAPER_MAX_F) <= tol
  );
}

export function isSquareCornerVertex(g: GridCreaseGraph, vIdx: number, tol = 1e-10): boolean {
  const [x, y] = g.pointsF[vIdx];
  const onX = Math.abs(x - PAPER_MIN_F) <= tol || Math.abs(x - PAPER_MAX_F) <= tol;
  const onY = Math.abs(y - PAPER_MIN_F) <= tol || Math.abs(y - PAPER_MAX_F) <= tol;
  return onX && onY;
}

export function onDiagVertex(g: GridCreaseGraph, vIdx: number, tol = 1e-10): boolean {
  const [x, y] = g.pointsF[vIdx];
  return Math.abs(x - y) <= tol;
}

export function diagonalSymmetryOk(g: GridCreaseGraph): boolean {
  for (const [i, j] of g.edgePairs()) {
    const mi = g.mirrorVertexIdx(i);
    const mj = g.mirrorVertexIdx(j);
    if (mi === null || mj === null) {
      return false;
    }
    if (!g.hasEdge(mi, mj)) {
      return false;
    }
  }
  return true;
}

export function cornersDiagSymmetric(corners: ReadonlyArray<PointE>): boolean {
  const keys = new Set(corners.map((p) => pointKey(p)));
  for (const p of corners) {
    const mk = pointKey({ x: p.y, y: p.x });
    if (!keys.has(mk)) {
      return false;
    }
  }
  return true;
}
