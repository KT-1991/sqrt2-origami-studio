import { HALF, add, q2Cmp, qsqrt2, qsqrt2Approx, sub } from "./qsqrt2";
import type { PointE, Qsqrt2, Vec2 } from "./types";

function cloneQsqrt2(z: Qsqrt2): Qsqrt2 {
  return { a: z.a, b: z.b, k: z.k };
}

function clonePointE(p: PointE): PointE {
  return {
    x: cloneQsqrt2(p.x),
    y: cloneQsqrt2(p.y),
  };
}

export function defaultOriginOffsetWorld(): PointE {
  // Backward-compatible default: current unit-square center.
  return {
    x: cloneQsqrt2(HALF),
    y: cloneQsqrt2(HALF),
  };
}

export const PAPER_MIN_Q: Qsqrt2 = qsqrt2(-1, 0, 1);
export const PAPER_MAX_Q: Qsqrt2 = HALF;
export const PAPER_MIN_F = -0.5;
export const PAPER_MAX_F = 0.5;
export const PAPER_CENTER_F = 0.0;

export function normalizeOriginOffsetWorld(offset?: PointE): PointE {
  if (!offset) {
    return defaultOriginOffsetWorld();
  }
  return clonePointE(offset);
}

export function worldToInternalQ(zWorld: Qsqrt2, offsetWorld: Qsqrt2): Qsqrt2 {
  // internal(centered) = world - origin
  return sub(zWorld, offsetWorld);
}

export function internalToWorldQ(zInternal: Qsqrt2, offsetWorld: Qsqrt2): Qsqrt2 {
  // world = internal(centered) + origin
  return add(zInternal, offsetWorld);
}

export function worldToInternalPoint(pWorld: PointE, originWorld: PointE): PointE {
  return {
    x: worldToInternalQ(pWorld.x, originWorld.x),
    y: worldToInternalQ(pWorld.y, originWorld.y),
  };
}

export function internalToWorldPoint(pInternal: PointE, originWorld: PointE): PointE {
  return {
    x: internalToWorldQ(pInternal.x, originWorld.x),
    y: internalToWorldQ(pInternal.y, originWorld.y),
  };
}

export function worldToInternalVec2(vWorld: Vec2, originWorld: PointE): Vec2 {
  const ox = qsqrt2Approx(originWorld.x);
  const oy = qsqrt2Approx(originWorld.y);
  return {
    x: vWorld.x - ox,
    y: vWorld.y - oy,
  };
}

export function internalToWorldVec2(vInternal: Vec2, originWorld: PointE): Vec2 {
  const ox = qsqrt2Approx(originWorld.x);
  const oy = qsqrt2Approx(originWorld.y);
  return {
    x: vInternal.x + ox,
    y: vInternal.y + oy,
  };
}

export function inCenteredPaperPointE(p: PointE): boolean {
  return (
    q2Cmp(p.x, PAPER_MIN_Q) >= 0 &&
    q2Cmp(p.x, PAPER_MAX_Q) <= 0 &&
    q2Cmp(p.y, PAPER_MIN_Q) >= 0 &&
    q2Cmp(p.y, PAPER_MAX_Q) <= 0
  );
}

export function inCenteredPaperVec2(v: Vec2, eps = 1e-12): boolean {
  return (
    v.x >= PAPER_MIN_F - eps &&
    v.x <= PAPER_MAX_F + eps &&
    v.y >= PAPER_MIN_F - eps &&
    v.y <= PAPER_MAX_F + eps
  );
}
