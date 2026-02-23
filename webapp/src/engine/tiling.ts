import { resolveTilingRunInput } from "./defaults";
import type {
  KadoSpec,
  TilingLatticeConfig,
  TilingRunInput,
  TilingRunInputResolved,
  TilingState,
  Vec2,
} from "./types";
import {
  internalToWorldVec2,
  normalizeOriginOffsetWorld,
  worldToInternalVec2,
} from "./paper_frame";

type Point = [number, number];

interface IndependentVar {
  name: string;
  length: number;
  symmetry: "axis" | "pair_anchor";
  pairName?: string;
}

interface Circle {
  name: string;
  center: Point;
  radius: number;
}

const OCT_PHASE = Math.PI / 8.0;
const OCT_UNIT_VERTS: Point[] = Array.from({ length: 8 }, (_, k) => [
  Math.cos(OCT_PHASE + (2.0 * Math.PI * k) / 8.0),
  Math.sin(OCT_PHASE + (2.0 * Math.PI * k) / 8.0),
]);

const EPS = 1e-10;
const PAIR_KEY_SEP = "\u0001";

class SeededRandom {
  private state: number;

  constructor(seed: number) {
    this.state = (seed >>> 0) ^ 0x9e3779b9;
  }

  private nextU32(): number {
    this.state = (Math.imul(1664525, this.state) + 1013904223) >>> 0;
    return this.state;
  }

  random(): number {
    return this.nextU32() / 4294967296.0;
  }

  uniform(lo: number, hi: number): number {
    return lo + (hi - lo) * this.random();
  }

  randrange(n: number): number {
    if (!Number.isInteger(n) || n <= 0) {
      throw new Error("randrange(n): n must be a positive integer");
    }
    return Math.floor(this.random() * n);
  }
}

function pointToVec2(p: Point): Vec2 {
  return { x: p[0], y: p[1] };
}

function vec2ToPoint(v: Vec2): Point {
  return [v.x, v.y];
}

function clonePointMap(src: Record<string, Point>): Record<string, Point> {
  const out: Record<string, Point> = {};
  for (const [k, v] of Object.entries(src)) {
    out[k] = [v[0], v[1]];
  }
  return out;
}

function unitPolygonAxes(poly: Point[]): Point[] {
  const axes: Point[] = [];
  const n = poly.length;
  for (let i = 0; i < n; i += 1) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % n];
    const ex = x2 - x1;
    const ey = y2 - y1;
    const nx = -ey;
    const ny = ex;
    const l = Math.hypot(nx, ny);
    if (l <= 1e-15) {
      continue;
    }
    axes.push([nx / l, ny / l]);
  }
  return axes;
}

const OCT_AXES = unitPolygonAxes(OCT_UNIT_VERTS);
const OCT_AXIS_EXTENTS = OCT_AXES.map(([ax, ay]) =>
  Math.max(...OCT_UNIT_VERTS.map(([vx, vy]) => vx * ax + vy * ay)),
);

function mirrorYEqX(p: Point): Point {
  return [p[1], p[0]];
}

function dist(a: Point, b: Point): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

function buildIndependentVars(specs: KadoSpec[]): IndependentVar[] {
  const out: IndependentVar[] = [];
  const used = new Set<string>();
  const byName = new Map<string, KadoSpec>();
  for (const s of specs) {
    byName.set(s.name, s);
  }

  for (const s of specs) {
    if (used.has(s.name)) {
      continue;
    }
    if (s.symmetry === "axis") {
      out.push({
        name: s.name,
        length: s.length,
        symmetry: "axis",
      });
      used.add(s.name);
      continue;
    }
    if (s.symmetry === "pair") {
      const pair = s.pairName ? byName.get(s.pairName) : undefined;
      if (!pair || !s.pairName) {
        throw new Error(`pair spec missing valid pairName: ${s.name}`);
      }
      if (Math.abs(pair.length - s.length) > 1e-9) {
        throw new Error(`pair lengths must match: ${s.name}, ${pair.name}`);
      }
      out.push({
        name: s.name,
        length: s.length,
        symmetry: "pair_anchor",
        pairName: s.pairName,
      });
      used.add(s.name);
      used.add(s.pairName);
      continue;
    }
    throw new Error(`unknown symmetry: ${String((s as { symmetry: unknown }).symmetry)}`);
  }
  return out;
}

function expandCenters(
  indep: Record<string, Point>,
  vars_: IndependentVar[],
): Record<string, Point> {
  const out: Record<string, Point> = {};
  for (const v of vars_) {
    const c = indep[v.name];
    out[v.name] = [c[0], c[1]];
    if (v.symmetry === "pair_anchor" && v.pairName) {
      out[v.pairName] = mirrorYEqX(c);
    }
  }
  return out;
}

function circlesFromCenters(
  centers: Record<string, Point>,
  specs: KadoSpec[],
  alpha: number,
): Circle[] {
  const byName = new Map<string, KadoSpec>();
  for (const s of specs) {
    byName.set(s.name, s);
  }

  const out: Circle[] = [];
  for (const [name, center] of Object.entries(centers)) {
    const spec = byName.get(name);
    if (!spec) {
      continue;
    }
    out.push({
      name,
      center,
      radius: alpha * spec.length,
    });
  }
  return out;
}

function boundaryPenalty(center: Point): number {
  const [x, y] = center;
  let pen = 0.0;
  if (x < -0.5) {
    pen += (-0.5 - x) ** 2;
  }
  if (x > 0.5) {
    pen += (x - 0.5) ** 2;
  }
  if (y < -0.5) {
    pen += (-0.5 - y) ** 2;
  }
  if (y > 0.5) {
    pen += (y - 0.5) ** 2;
  }
  return pen;
}

function octOverlapDepthSameOrientation(
  centerA: Point,
  radiusA: number,
  centerB: Point,
  radiusB: number,
): number {
  const dx = centerA[0] - centerB[0];
  const dy = centerA[1] - centerB[1];
  let minDepth = 1e30;
  for (let i = 0; i < OCT_AXES.length; i += 1) {
    const [ax, ay] = OCT_AXES[i];
    const extent = OCT_AXIS_EXTENTS[i];
    const sep = Math.abs(dx * ax + dy * ay);
    const ha = radiusA * extent;
    const hb = radiusB * extent;
    const depth = Math.min(ha + hb - sep, 2.0 * Math.min(ha, hb));
    if (depth <= EPS) {
      return 0.0;
    }
    if (depth < minDepth) {
      minDepth = depth;
    }
  }
  return minDepth <= EPS ? 0.0 : minDepth;
}

function octPairOverlapPenalty(
  centerA: Point,
  radiusA: number,
  centerB: Point,
  radiusB: number,
  margin = 0.0,
): number {
  const dx = centerA[0] - centerB[0];
  const dy = centerA[1] - centerB[1];
  const rr = radiusA + radiusB;
  if (dx * dx + dy * dy >= rr * rr) {
    return 0.0;
  }
  const depth = octOverlapDepthSameOrientation(centerA, radiusA, centerB, radiusB);
  if (depth <= 0.0) {
    return 0.0;
  }
  return (depth + margin) ** 2 * 16.0;
}

function packingPenalty(circles: Circle[], margin = 0.0): number {
  let pen = 0.0;
  for (const c of circles) {
    pen += boundaryPenalty(c.center);
  }
  for (let i = 0; i < circles.length; i += 1) {
    for (let j = i + 1; j < circles.length; j += 1) {
      pen += octPairOverlapPenalty(
        circles[i].center,
        circles[i].radius,
        circles[j].center,
        circles[j].radius,
        margin,
      );
    }
  }
  return pen;
}

function contactScore(circles: Circle[]): number {
  let score = 0.0;
  for (let i = 0; i < circles.length; i += 1) {
    for (let j = i + 1; j < circles.length; j += 1) {
      const ci = circles[i];
      const cj = circles[j];
      const d = dist(ci.center, cj.center);
      const target = ci.radius + cj.radius;
      const delta = Math.abs(d - target);
      const w = Math.abs(ci.radius - cj.radius) <= 1e-9 ? 2.0 : 1.0;
      score += w / (1.0 + delta);
    }
  }
  return score;
}

function regularOctVertices(center: Point, radius: number): Point[] {
  const [cx, cy] = center;
  return OCT_UNIT_VERTS.map(([ux, uy]) => [cx + radius * ux, cy + radius * uy]);
}

function cornerHits(
  centers: Record<string, Point>,
  specs: KadoSpec[],
  alpha: number,
  tol = 1e-3,
): number {
  const corners: Point[] = [
    [-0.5, -0.5],
    [-0.5, 0.5],
    [0.5, -0.5],
    [0.5, 0.5],
  ];
  const byName = new Map<string, KadoSpec>();
  for (const s of specs) {
    byName.set(s.name, s);
  }

  const vertices: Point[] = [];
  for (const [name, center] of Object.entries(centers)) {
    const spec = byName.get(name);
    if (!spec) {
      continue;
    }
    vertices.push(...regularOctVertices(center, alpha * spec.length));
  }

  let hit = 0;
  for (const q of corners) {
    let best = 1e30;
    for (const v of vertices) {
      best = Math.min(best, dist(v, q));
    }
    if (best <= tol) {
      hit += 1;
    }
  }
  return hit;
}

function randInitIndependent(
  vars_: IndependentVar[],
  rng: SeededRandom,
): Record<string, Point> {
  const out: Record<string, Point> = {};
  for (const v of vars_) {
    if (v.symmetry === "axis") {
      const t = rng.uniform(-0.5, 0.5);
      out[v.name] = [t, t];
    } else {
      let x = rng.uniform(-0.5, 0.5);
      let y = rng.uniform(-0.5, 0.5);
      if (y > x) {
        [x, y] = [y, x];
      }
      out[v.name] = [x, y];
    }
  }
  return out;
}

function projectPointToSymmetry(p: Point, symmetry: "axis" | "pair_anchor"): Point {
  let x = Math.min(0.5, Math.max(-0.5, p[0]));
  let y = Math.min(0.5, Math.max(-0.5, p[1]));
  if (symmetry === "axis") {
    let t = 0.5 * (x + y);
    t = Math.min(0.5, Math.max(-0.5, t));
    return [t, t];
  }
  if (y > x) {
    [x, y] = [y, x];
  }
  return [x, y];
}

function normalizeIndependentHint(
  hint: Record<string, Point>,
  vars_: IndependentVar[],
): Record<string, Point> {
  const byName = new Map<string, IndependentVar>();
  for (const v of vars_) {
    byName.set(v.name, v);
  }
  const out: Record<string, Point> = {};
  for (const [name, p] of Object.entries(hint)) {
    const v = byName.get(name);
    if (!v) {
      continue;
    }
    out[name] = projectPointToSymmetry(p, v.symmetry);
  }
  return out;
}

function independentHintFromCenters(
  centers: Record<string, Point>,
  vars_: IndependentVar[],
): Record<string, Point> {
  const out: Record<string, Point> = {};
  for (const v of vars_) {
    let c: Point | undefined;
    if (v.name in centers) {
      c = centers[v.name];
    } else if (v.symmetry === "pair_anchor" && v.pairName && v.pairName in centers) {
      c = mirrorYEqX(centers[v.pairName]);
    }
    if (!c) {
      continue;
    }
    out[v.name] = projectPointToSymmetry(c, v.symmetry);
  }
  return out;
}

function guidedInitIndependent(
  vars_: IndependentVar[],
  hint: Record<string, Point>,
  rng: SeededRandom,
  jitter: number,
): Record<string, Point> {
  const out = randInitIndependent(vars_, rng);
  for (const v of vars_) {
    const p = hint[v.name];
    if (!p) {
      continue;
    }
    let [x, y] = p;
    if (jitter > 0.0) {
      x += rng.uniform(-jitter, jitter);
      y += rng.uniform(-jitter, jitter);
    }
    out[v.name] = projectPointToSymmetry([x, y], v.symmetry);
  }
  return out;
}

function perturbPoint(
  p: Point,
  symmetry: "axis" | "pair_anchor",
  step: number,
  rng: SeededRandom,
): Point {
  let x = p[0] + rng.uniform(-step, step);
  let y = p[1] + rng.uniform(-step, step);
  x = Math.min(0.5, Math.max(-0.5, x));
  y = Math.min(0.5, Math.max(-0.5, y));
  if (symmetry === "axis") {
    let t = 0.5 * (x + y);
    t = Math.min(0.5, Math.max(-0.5, t));
    return [t, t];
  }
  if (y > x) {
    [x, y] = [y, x];
  }
  return [x, y];
}

function continuousPack(
  specs: KadoSpec[],
  vars_: IndependentVar[],
  alpha: number,
  seed: number,
  restarts: number,
  iters: number,
  initialIndependent?: Record<string, Point>,
  guidedRestarts = 0,
  guidedJitter = 0.08,
): [Record<string, Point>, number] {
  const rng = new SeededRandom(seed);
  let bestIndependent: Record<string, Point> = {};
  let bestPen = 1e30;
  const hint = initialIndependent ? normalizeIndependentHint(initialIndependent, vars_) : {};
  const guidedSlots =
    Object.keys(hint).length > 0 ? Math.min(restarts, Math.max(1, guidedRestarts)) : 0;

  for (let rr = 0; rr < restarts; rr += 1) {
    const rrRng = new SeededRandom(seed + 1009 * rr);
    let indep: Record<string, Point>;
    if (rr < guidedSlots) {
      const jitter = rr === 0 ? 0.0 : guidedJitter * 0.65 ** (rr - 1);
      indep = guidedInitIndependent(vars_, hint, rrRng, jitter);
    } else {
      indep = randInitIndependent(vars_, rrRng);
    }

    let step = 0.14;
    let curPen = packingPenalty(circlesFromCenters(expandCenters(indep, vars_), specs, alpha));
    for (let it = 0; it < iters; it += 1) {
      const v = vars_[rng.randrange(vars_.length)];
      const old = indep[v.name];
      indep[v.name] = perturbPoint(old, v.symmetry, step, rng);
      const pen2 = packingPenalty(circlesFromCenters(expandCenters(indep, vars_), specs, alpha));
      if (pen2 <= curPen) {
        curPen = pen2;
      } else {
        indep[v.name] = old;
      }
      step *= 0.9992;
    }
    if (curPen < bestPen) {
      bestPen = curPen;
      bestIndependent = clonePointMap(indep);
    }
  }
  return [bestIndependent, bestPen];
}

const latticeCache = new Map<string, number[]>();

function latticeValues(config: TilingLatticeConfig): number[] {
  const key = `${config.aMax}:${config.bMax}:${config.kMax}`;
  const cached = latticeCache.get(key);
  if (cached) {
    return cached;
  }
  const vals = new Set<number>();
  const root2 = Math.sqrt(2.0);
  for (let k = 0; k <= config.kMax; k += 1) {
    const den = 2 ** k;
    for (let a = -config.aMax; a <= config.aMax; a += 1) {
      for (let b = -config.bMax; b <= config.bMax; b += 1) {
        const v = (a + b * root2) / den;
        if (v >= -0.5 - 1e-9 && v <= 0.5 + 1e-9) {
          vals.add(Math.min(0.5, Math.max(-0.5, v)));
        }
      }
    }
  }
  for (let k = 0; k <= config.kMax; k += 1) {
    const den = 2 ** k;
    for (let a = -config.aMax; a <= config.aMax; a += 1) {
      const v = a / den;
      if (v >= -0.5 - 1e-9 && v <= 0.5 + 1e-9) {
        vals.add(Math.min(0.5, Math.max(-0.5, v)));
      }
    }
    for (let b = -config.bMax; b <= config.bMax; b += 1) {
      const v = (b * root2) / den;
      if (v >= -0.5 - 1e-9 && v <= 0.5 + 1e-9) {
        vals.add(Math.min(0.5, Math.max(-0.5, v)));
      }
    }
  }
  vals.add(-0.5);
  vals.add(0.0);
  vals.add(0.5);
  const out = Array.from(vals.values()).sort((x, y) => x - y);
  latticeCache.set(key, out);
  return out;
}

function nearestValue(v: number, vals: number[]): number {
  let best = vals[0];
  let bestD = Math.abs(best - v);
  for (let i = 1; i < vals.length; i += 1) {
    const d = Math.abs(vals[i] - v);
    if (d < bestD) {
      bestD = d;
      best = vals[i];
    }
  }
  return best;
}

function bisectLeft(vals: number[], v: number): number {
  let lo = 0;
  let hi = vals.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (vals[mid] < v) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

function nearestValues(v: number, vals: number[], limit: number): number[] {
  if (limit >= vals.length) {
    return [...vals];
  }
  const idx = bisectLeft(vals, v);
  let left = idx - 1;
  let right = idx;
  const out: number[] = [];
  while (out.length < limit && (left >= 0 || right < vals.length)) {
    if (left < 0) {
      out.push(vals[right]);
      right += 1;
      continue;
    }
    if (right >= vals.length) {
      out.push(vals[left]);
      left -= 1;
      continue;
    }
    if (Math.abs(vals[left] - v) <= Math.abs(vals[right] - v)) {
      out.push(vals[left]);
      left -= 1;
    } else {
      out.push(vals[right]);
      right += 1;
    }
  }
  return out;
}

function snapIndependent(
  indep: Record<string, Point>,
  vars_: IndependentVar[],
  vals: number[],
): Record<string, Point> {
  const out: Record<string, Point> = {};
  for (const v of vars_) {
    const [x, y] = indep[v.name];
    if (v.symmetry === "axis") {
      const t = nearestValue(0.5 * (x + y), vals);
      out[v.name] = [t, t];
    } else {
      let sx = nearestValue(x, vals);
      let sy = nearestValue(y, vals);
      if (sy > sx) {
        [sx, sy] = [sy, sx];
      }
      out[v.name] = [sx, sy];
    }
  }
  return out;
}

function pairKey(a: string, b: string): string {
  return a < b ? `${a}${PAIR_KEY_SEP}${b}` : `${b}${PAIR_KEY_SEP}${a}`;
}

function pairKeyParts(key: string): [string, string] {
  const parts = key.split(PAIR_KEY_SEP);
  return [parts[0], parts[1]];
}

function localRepairSnap(
  indep: Record<string, Point>,
  vars_: IndependentVar[],
  specs: KadoSpec[],
  alpha: number,
  vals: number[],
  rounds = 4,
): Record<string, Point> {
  const out = clonePointMap(indep);
  const byName = new Map<string, KadoSpec>();
  const radii = new Map<string, number>();
  for (const s of specs) {
    byName.set(s.name, s);
    radii.set(s.name, alpha * s.length);
  }

  const order = [...vars_].sort((lhs, rhs) => {
    const ll = byName.get(lhs.name)?.length ?? 0.0;
    const rr = byName.get(rhs.name)?.length ?? 0.0;
    return ll - rr;
  });

  const centers = expandCenters(out, vars_);
  const allNames = Object.keys(centers).sort();

  const depNames = new Map<string, string[]>();
  const affectedPairs = new Map<string, string[]>();
  for (const v of vars_) {
    const dep = [v.name];
    if (v.symmetry === "pair_anchor" && v.pairName) {
      dep.push(v.pairName);
    }
    const depUniq = [...new Set(dep)].sort();
    depNames.set(v.name, depUniq);
    const aff = new Set<string>();
    for (const a of depUniq) {
      for (const b of allNames) {
        if (a === b) {
          continue;
        }
        aff.add(pairKey(a, b));
      }
    }
    affectedPairs.set(v.name, [...aff].sort());
  }

  const boundaryByName = new Map<string, number>();
  for (const name of allNames) {
    boundaryByName.set(name, boundaryPenalty(centers[name]));
  }

  const pairPen = new Map<string, number>();
  let totalPen = 0.0;
  for (const v of boundaryByName.values()) {
    totalPen += v;
  }

  for (let i = 0; i < allNames.length; i += 1) {
    const ni = allNames[i];
    const ci = centers[ni];
    const ri = radii.get(ni) ?? 0.0;
    for (let j = i + 1; j < allNames.length; j += 1) {
      const nj = allNames[j];
      const p = octPairOverlapPenalty(ci, ri, centers[nj], radii.get(nj) ?? 0.0);
      const k = pairKey(ni, nj);
      pairPen.set(k, p);
      totalPen += p;
    }
  }

  for (let rr = 0; rr < rounds; rr += 1) {
    for (const v of order) {
      const [ox, oy] = out[v.name];
      let candidates: Point[] = [];
      if (v.symmetry === "axis") {
        candidates = nearestValues(0.5 * (ox + oy), vals, 18).map((t) => [t, t]);
      } else {
        const nearX = nearestValues(ox, vals, 10);
        const nearY = nearestValues(oy, vals, 10);
        const uniq = new Set<string>();
        for (const x0 of nearX) {
          for (const y0 of nearY) {
            let x = x0;
            let y = y0;
            if (y > x) {
              [x, y] = [y, x];
            }
            const k = `${x},${y}`;
            if (!uniq.has(k)) {
              uniq.add(k);
            }
          }
        }
        candidates = [...uniq].map((it) => {
          const [xs, ys] = it.split(",");
          return [Number(xs), Number(ys)];
        });
      }

      const dep = depNames.get(v.name) ?? [];
      const affPairs = affectedPairs.get(v.name) ?? [];
      let oldContrib = 0.0;
      for (const name of dep) {
        oldContrib += boundaryByName.get(name) ?? 0.0;
      }
      for (const k of affPairs) {
        oldContrib += pairPen.get(k) ?? 0.0;
      }

      let best = out[v.name];
      let bestPen = totalPen;
      for (const c of candidates) {
        const trialCenters: Record<string, Point> = { [v.name]: c };
        if (v.symmetry === "pair_anchor" && v.pairName) {
          trialCenters[v.pairName] = mirrorYEqX(c);
        }

        let newContrib = 0.0;
        for (const name of dep) {
          const tp = trialCenters[name];
          if (!tp) {
            continue;
          }
          newContrib += boundaryPenalty(tp);
        }

        for (const k of affPairs) {
          const [a, b] = pairKeyParts(k);
          const ca = trialCenters[a] ?? centers[a];
          const cb = trialCenters[b] ?? centers[b];
          newContrib += octPairOverlapPenalty(
            ca,
            radii.get(a) ?? 0.0,
            cb,
            radii.get(b) ?? 0.0,
          );
        }

        const p = totalPen - oldContrib + newContrib;
        if (p + 1e-15 < bestPen) {
          bestPen = p;
          best = c;
        }
      }

      if (best[0] !== out[v.name][0] || best[1] !== out[v.name][1]) {
        out[v.name] = best;
        centers[v.name] = best;
        if (v.symmetry === "pair_anchor" && v.pairName) {
          centers[v.pairName] = mirrorYEqX(best);
        }

        for (const name of dep) {
          boundaryByName.set(name, boundaryPenalty(centers[name]));
        }
        for (const k of affPairs) {
          const [a, b] = pairKeyParts(k);
          pairPen.set(
            k,
            octPairOverlapPenalty(
              centers[a],
              radii.get(a) ?? 0.0,
              centers[b],
              radii.get(b) ?? 0.0,
            ),
          );
        }
        totalPen = bestPen;
      }
    }
  }
  return out;
}

function solveKadoLayoutResolved(input: TilingRunInputResolved): TilingState {
  const specs = input.specs;
  if (specs.length === 0) {
    throw new Error("specs must not be empty");
  }

  const lattice = input.lattice;
  const latticeVals = latticeValues(lattice);
  const denSummary = 2 ** lattice.kMax;
  const coeffSummary = Math.max(1, lattice.aMax, lattice.bMax);

  const vars_ = buildIndependentVars(specs);
  const maxLen = Math.max(...specs.map((s) => s.length));
  if (!(maxLen > 0.0)) {
    throw new Error("all lengths must be > 0");
  }
  let lo = 0.0;
  let hi = 0.5 / maxLen;
  let best: TilingState | undefined;

  const manualHint: Record<string, Point> = {};
  if (input.initialCenters) {
    const centers: Record<string, Point> = {};
    for (const [k, v] of Object.entries(input.initialCenters)) {
      centers[k] = vec2ToPoint(v);
    }
    Object.assign(manualHint, independentHintFromCenters(centers, vars_));
  }
  if (input.initialIndependent) {
    const indep: Record<string, Point> = {};
    for (const [k, v] of Object.entries(input.initialIndependent)) {
      indep[k] = vec2ToPoint(v);
    }
    Object.assign(manualHint, normalizeIndependentHint(indep, vars_));
  }

  let warmHint: Record<string, Point> | undefined;

  for (let step = 0; step < input.alphaSteps; step += 1) {
    const alpha = 0.5 * (lo + hi);
    let startHint: Record<string, Point> | undefined;
    if (input.warmStart && warmHint) {
      startHint = warmHint;
    }
    if (!startHint && Object.keys(manualHint).length > 0) {
      startHint = manualHint;
    }

    const [indepCont] = continuousPack(
      specs,
      vars_,
      alpha,
      input.seed + 17 * denSummary + 101 * coeffSummary,
      input.packRestarts,
      input.packIters,
      startHint,
      input.packGuidedRestarts,
      input.packGuidedJitter,
    );
    if (input.warmStart) {
      warmHint = clonePointMap(indepCont);
    }

    const indepSnap = snapIndependent(indepCont, vars_, latticeVals);
    const indepFix = localRepairSnap(indepSnap, vars_, specs, alpha, latticeVals);
    const centers = expandCenters(indepFix, vars_);
    const circles = circlesFromCenters(centers, specs, alpha);
    const pen = packingPenalty(circles);
    if (pen <= 1e-10) {
      const cur: TilingState = {
        ok: true,
        alpha,
        lattice,
        den: denSummary,
        coeffLimit: coeffSummary,
        centers: Object.fromEntries(
          Object.entries(centers).map(([name, p]) => [name, pointToVec2(p)]),
        ),
        cornerHits: cornerHits(centers, specs, alpha),
        contactScore: contactScore(circles),
        message: "feasible",
      };
      lo = alpha;
      best = cur;
    } else {
      hi = alpha;
    }
  }

  if (!best) {
    return {
      ok: false,
      alpha: 0.0,
      lattice,
      den: denSummary,
      coeffLimit: coeffSummary,
      centers: {},
      cornerHits: 0,
      contactScore: 0.0,
      message: "no feasible layout found",
    };
  }
  return best;
}

export function runTiling(input: TilingRunInput): TilingState {
  const resolved = resolveTilingRunInput(input);
  const originOffset = normalizeOriginOffsetWorld(resolved.originOffset);

  const initialCentersInternal = resolved.initialCenters
    ? Object.fromEntries(
        Object.entries(resolved.initialCenters).map(([name, v]) => [
          name,
          worldToInternalVec2(v, originOffset),
        ]),
      )
    : undefined;
  const initialIndependentInternal = resolved.initialIndependent
    ? Object.fromEntries(
        Object.entries(resolved.initialIndependent).map(([name, v]) => [
          name,
          worldToInternalVec2(v, originOffset),
        ]),
      )
    : undefined;

  const internalState = solveKadoLayoutResolved({
    ...resolved,
    initialCenters: initialCentersInternal,
    initialIndependent: initialIndependentInternal,
  });
  if (!internalState.ok) {
    return internalState;
  }

  return {
    ...internalState,
    centers: Object.fromEntries(
      Object.entries(internalState.centers).map(([name, v]) => [
        name,
        internalToWorldVec2(v, originOffset),
      ]),
    ),
  };
}
