<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { WorkerOrigamiEngine } from "../src/engine/client";
import { memGraphToCpGraphV1 } from "../src/engine/cp_graph_adapters";
import {
  DEFAULT_REAL_DATA_EVAL_PROFILES,
  type CreasegenProfileEvaluation,
} from "../src/engine/creasegen_profiles";
import {
  add,
  sub,
  fromDyadic,
  fromInt,
  q2Cmp,
  qsqrt2,
  qsqrt2Approx,
} from "../src/engine/qsqrt2";
import type {
  CreaseGraphMem,
  CreaseSeedEdgeInput,
  CreaseSeedSegmentInput,
  CpGraphV1Json,
  FoldPreviewResult,
  KadoSpec,
  PointE,
  Qsqrt2,
  TilingRunInput,
  TilingState,
  Vec2,
} from "../src/engine/types";

interface DesignerPoint {
  id: number;
  x: number;
  y: number;
  size: number;
}

interface LatticeValue {
  key: string;
  exact: Qsqrt2;
  approx: number;
}

interface EdgePick {
  key: string;
  point: PointE;
  x: number;
  y: number;
  cornerIdx: number | null;
}

type DesignerGroup = "axis" | "side" | "free";
type CpGraphExportPolicy = "centered_world" | "legacy_unit";

const CANVAS_SIZE = 360;
const CP_VIEW_SIZE = 460;
const FOLD_VIEW_SIZE = 460;

const PAPER_MIN = -0.5;
const PAPER_MAX = 0.5;
const PAPER_MIN_Q = qsqrt2(-1, 0, 1);
const PAPER_MAX_Q = qsqrt2(1, 0, 1);

function clampPaper(v: number): number {
  return Math.min(PAPER_MAX, Math.max(PAPER_MIN, v));
}

function clampInt(v: number, min: number, max: number): number {
  if (!Number.isFinite(v)) {
    return min;
  }
  return Math.max(min, Math.min(max, Math.round(v)));
}

function num(v: number): string {
  return Number.isFinite(v) ? String(v) : "-";
}

const uiLang = ref<"ja" | "en">("ja");

function tr(ja: string, en: string): string {
  return uiLang.value === "ja" ? ja : en;
}

// Edit author/SNS fields here when finalized.
const APP_INFO = {
  summaryJa:
    "折り紙の展開図を、(a+b√2)/2^k 格子ベースで設計・最適化・検証するためのクライアント完結Webアプリです。",
  summaryEn:
    "A client-only web app for designing, optimizing, and validating origami crease patterns on the (a+b*sqrt(2))/2^k lattice.",
  flowJa: "配置 → タイリング最適化 → 展開図生成 → 折り上がり推定",
  flowEn: "Placement -> Tiling optimization -> Crease generation -> Folded preview",
  authorName: "11田",
  socialLinks: [
    { label: "X / Twitter ", url: "https://x.com/11da_origami" },
  ],
  repositoryUrl: "https://github.com/KT-1991/sqrt2-origami-studio",
  licenseName: "MIT",
} as const;

function pointExactKey(p: PointE): string {
  return `${p.x.a.toString()}_${p.x.b.toString()}_${p.x.k}|${p.y.a.toString()}_${p.y.b.toString()}_${p.y.k}`;
}

function mirroredPointExactKey(p: PointE): string {
  return pointExactKey(mirrorPointExactByLocalDiag(p));
}

function qsqrt2Short(z: PointE["x"]): string {
  return `${z.a.toString()},${z.b.toString()},${z.k}`;
}

function qsqrt2Expr(z: Qsqrt2): string {
  const a = z.a;
  const b = z.b;
  const hasA = a !== 0n;
  const hasB = b !== 0n;
  let numer = "0";
  if (hasA && hasB) {
    const bAbs = b < 0n ? -b : b;
    numer = `${a.toString()}${b < 0n ? "-" : "+"}${bAbs.toString()}√2`;
  } else if (hasB) {
    numer = `${b.toString()}√2`;
  } else if (hasA) {
    numer = a.toString();
  }
  if (z.k <= 0) {
    return numer;
  }
  const den = (1n << BigInt(z.k)).toString();
  return `(${numer})/${den}`;
}

function qsqrt2Key(z: Qsqrt2): string {
  return `${z.a.toString()}_${z.b.toString()}_${z.k}`;
}

function pointExactLabel(p: PointE): string {
  return `x(${qsqrt2Short(p.x)}) y(${qsqrt2Short(p.y)})`;
}

function pointApproxLabel(p: PointE): string {
  return `(${qsqrt2Approx(p.x).toFixed(3)}, ${qsqrt2Approx(p.y).toFixed(3)})`;
}

const originOffsetExact = computed<PointE>(() => ({
  x: qsqrt2(
    Math.trunc(originOffsetDraft.value.xA),
    Math.trunc(originOffsetDraft.value.xB),
    clampInt(originOffsetDraft.value.xK, 0, 16),
  ),
  y: qsqrt2(
    Math.trunc(originOffsetDraft.value.yA),
    Math.trunc(originOffsetDraft.value.yB),
    clampInt(originOffsetDraft.value.yK, 0, 16),
  ),
}));

const originOffsetApprox = computed(() => ({
  x: qsqrt2Approx(originOffsetExact.value.x),
  y: qsqrt2Approx(originOffsetExact.value.y),
}));

const paperWindow = computed(() => ({
  xMin: originOffsetApprox.value.x + PAPER_MIN,
  xMax: originOffsetApprox.value.x + PAPER_MAX,
  yMin: originOffsetApprox.value.y + PAPER_MIN,
  yMax: originOffsetApprox.value.y + PAPER_MAX,
}));

const paperWindowExact = computed(() => ({
  xMin: add(originOffsetExact.value.x, PAPER_MIN_Q),
  xMax: add(originOffsetExact.value.x, PAPER_MAX_Q),
  yMin: add(originOffsetExact.value.y, PAPER_MIN_Q),
  yMax: add(originOffsetExact.value.y, PAPER_MAX_Q),
}));

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function clampWorldX(v: number): number {
  return Math.min(paperWindow.value.xMax, Math.max(paperWindow.value.xMin, v));
}

function clampWorldY(v: number): number {
  return Math.min(paperWindow.value.yMax, Math.max(paperWindow.value.yMin, v));
}

function worldToLocalX(v: number): number {
  return v - originOffsetApprox.value.x;
}

function worldToLocalY(v: number): number {
  return v - originOffsetApprox.value.y;
}

function localToWorldX(v: number): number {
  return v + originOffsetApprox.value.x;
}

function localToWorldY(v: number): number {
  return v + originOffsetApprox.value.y;
}

function worldToCanvasUnitX(v: number): number {
  const span = Math.max(1e-12, paperWindow.value.xMax - paperWindow.value.xMin);
  return clamp01((clampWorldX(v) - paperWindow.value.xMin) / span);
}

function worldToCanvasUnitY(v: number): number {
  const span = Math.max(1e-12, paperWindow.value.yMax - paperWindow.value.yMin);
  return clamp01((clampWorldY(v) - paperWindow.value.yMin) / span);
}

function canvasUnitToWorldX(v: number): number {
  const span = paperWindow.value.xMax - paperWindow.value.xMin;
  return paperWindow.value.xMin + clamp01(v) * span;
}

function canvasUnitToWorldY(v: number): number {
  const span = paperWindow.value.yMax - paperWindow.value.yMin;
  return paperWindow.value.yMin + clamp01(v) * span;
}

function mirrorPointExactByLocalDiag(p: PointE): PointE {
  const ox = originOffsetExact.value.x;
  const oy = originOffsetExact.value.y;
  return {
    x: add(sub(p.y, oy), ox),
    y: add(sub(p.x, ox), oy),
  };
}

function mirrorApproxByLocalDiag(x: number, y: number): { x: number; y: number } {
  const ox = originOffsetApprox.value.x;
  const oy = originOffsetApprox.value.y;
  return {
    x: y - oy + ox,
    y: x - ox + oy,
  };
}

function foldFaceFill(depth: number, minDepth: number, maxDepth: number): string {
  const t = maxDepth > minDepth ? (depth - minDepth) / (maxDepth - minDepth) : 0;
  const light = 92 - t * 22;
  return `hsl(205 28% ${light}%)`;
}

function foldFaceOpacity(depth: number, minDepth: number, maxDepth: number): number {
  const t = maxDepth > minDepth ? (depth - minDepth) / (maxDepth - minDepth) : 0;
  return 0.22 + t * 0.42;
}

function normalizeSeedEdgePair(
  iRaw: number,
  jRaw: number,
  cornerCount: number,
): CreaseSeedEdgeInput | null {
  const i = Math.trunc(iRaw);
  const j = Math.trunc(jRaw);
  if (!Number.isInteger(i) || !Number.isInteger(j)) {
    return null;
  }
  if (cornerCount <= 1) {
    return null;
  }
  if (i < 0 || j < 0 || i >= cornerCount || j >= cornerCount || i === j) {
    return null;
  }
  return i < j ? { cornerI: i, cornerJ: j } : { cornerI: j, cornerJ: i };
}

const worker = new Worker(new URL("../src/workers/origami_engine.worker.ts", import.meta.url), {
  type: "module",
});
const engine = new WorkerOrigamiEngine(worker);

const busy = ref(false);
const progressRatio = ref(0);
const progressMessage = ref<string>("");
const progressStage = ref<string>("idle");
const progressRatioClamped = computed(() => Math.min(1, Math.max(0, progressRatio.value)));
const progressRingRadius = 54;
const progressRingCircumference = 2 * Math.PI * progressRingRadius;
const evaluations = ref<CreasegenProfileEvaluation[]>([]);
const bestProfileName = ref<string>("");
const selectedProfileName = ref<string>("");
const previewResult = ref<FoldPreviewResult | null>(null);
const previewProfileName = ref<string>("");
const previewAlpha = ref(0.0);
const previewLineWidth = ref(1.5);
const previewShowFaceId = ref(true);
const errorMessage = ref<string>("");
const lastRunAt = ref<string>("");
const leftPaneTab = ref<"run" | "global" | "points" | "generation" | "info">("run");

const symmetryEnabled = ref(true);
const placementMode = ref<"axis" | "side">("side");
const aMaxInput = ref(2);
const bMaxInput = ref(2);
const kMaxInput = ref(2);

const tilingSeed = ref(0);
const tilingAlphaSteps = ref(14);
const tilingPackRestarts = ref(10);
const tilingPackIters = ref(700);
const tilingState = ref<TilingState | null>(null);
const searchMaxDepthInput = ref(6);
const searchBranchPerNodeInput = ref(4);
const searchMaxNodesInput = ref(300);
const searchAllowViolationsInput = ref(0);
const searchDirTopKInput = ref(4);
const searchPriorityTopNInput = ref(6);

const cpGraphExportPolicy = ref<CpGraphExportPolicy>("centered_world");
const seedEdges = ref<CreaseSeedEdgeInput[]>([]);
const seedEdgeAutoMirror = ref(true);
const seedSegments = ref<CreaseSeedSegmentInput[]>([]);
const seedSegmentAutoMirror = ref(true);
const originOffsetDraft = ref({
  xA: 0,
  xB: 0,
  xK: 0,
  yA: 0,
  yB: 0,
  yK: 0,
});

const nextPointId = ref(1);
const axisPoints = ref<DesignerPoint[]>([{ id: nextPointId.value++, x: 0, y: 0, size: 1 }]);
const sidePoints = ref<DesignerPoint[]>([]);
const freePoints = ref<DesignerPoint[]>([{ id: nextPointId.value++, x: 0, y: 0, size: 1 }]);
const showDesignerGrid = ref(true);
const canvasEditMode = ref<"point" | "edge">("point");
const edgeDraftStartPick = ref<EdgePick | null>(null);
const edgeDraftPointer = ref<{ x: number; y: number } | null>(null);
const edgeDragStartPick = ref<EdgePick | null>(null);
const edgeDragMoved = ref(false);

const designerSvg = ref<SVGSVGElement | null>(null);
const dragState = ref<{ group: DesignerGroup; id: number } | null>(null);
const selectedPoint = ref<{ group: DesignerGroup; id: number } | null>(null);

const tilingLatticeConfig = computed(() => {
  const aMax = clampInt(aMaxInput.value, 1, 24);
  const bMax = clampInt(bMaxInput.value, 1, 24);
  const kMax = clampInt(kMaxInput.value, 0, 8);
  return {
    aMax,
    bMax,
    kMax,
  };
});

function buildWorldLatticeValues(minQ: Qsqrt2, maxQ: Qsqrt2): LatticeValue[] {
  const aMax = clampInt(aMaxInput.value, 1, 24);
  const bMax = clampInt(bMaxInput.value, 1, 24);
  const kMax = clampInt(kMaxInput.value, 0, 8);
  const byKey = new Map<string, LatticeValue>();
  for (let k = 0; k <= kMax; k += 1) {
    for (let a = -aMax; a <= aMax; a += 1) {
      for (let b = -bMax; b <= bMax; b += 1) {
        const z = qsqrt2(a, b, k);
        if (q2Cmp(z, minQ) < 0 || q2Cmp(z, maxQ) > 0) {
          continue;
        }
        const key = qsqrt2Key(z);
        if (byKey.has(key)) {
          continue;
        }
        byKey.set(key, {
          key,
          exact: z,
          approx: qsqrt2Approx(z),
        });
      }
    }
  }
  const out = [...byKey.values()].sort((lhs, rhs) => lhs.approx - rhs.approx);
  if (out.length > 0) {
    return out;
  }
  const minKey = qsqrt2Key(minQ);
  const maxKey = qsqrt2Key(maxQ);
  if (minKey === maxKey) {
    return [{ key: minKey, exact: minQ, approx: qsqrt2Approx(minQ) }];
  }
  return [
    { key: minKey, exact: minQ, approx: qsqrt2Approx(minQ) },
    { key: maxKey, exact: maxQ, approx: qsqrt2Approx(maxQ) },
  ];
}

const latticeXValues = computed<LatticeValue[]>(() =>
  buildWorldLatticeValues(paperWindowExact.value.xMin, paperWindowExact.value.xMax),
);

const latticeYValues = computed<LatticeValue[]>(() =>
  buildWorldLatticeValues(paperWindowExact.value.yMin, paperWindowExact.value.yMax),
);

function minLatticeStep(values: LatticeValue[]): number {
  if (values.length <= 1) {
    return Number.POSITIVE_INFINITY;
  }
  let minStep = Number.POSITIVE_INFINITY;
  for (let i = 1; i < values.length; i += 1) {
    const d = Math.abs(values[i].approx - values[i - 1].approx);
    if (d > 1e-12 && d < minStep) {
      minStep = d;
    }
  }
  return minStep;
}

const latticeStep = computed(() => {
  const minStep = Math.min(
    minLatticeStep(latticeXValues.value),
    minLatticeStep(latticeYValues.value),
  );
  if (!Number.isFinite(minStep)) {
    return 0.001;
  }
  return Number(minStep.toPrecision(8));
});

function nearestLatticeIndex(values: LatticeValue[], vIn: number): number {
  if (values.length <= 1) {
    return 0;
  }
  const minV = values[0].approx;
  const maxV = values[values.length - 1].approx;
  const v = Math.min(maxV, Math.max(minV, vIn));
  let lo = 0;
  let hi = values.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (values[mid].approx < v) {
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  const i1 = Math.max(0, Math.min(values.length - 1, lo));
  const i0 = Math.max(0, Math.min(values.length - 1, lo - 1));
  const d0 = Math.abs(values[i0].approx - v);
  const d1 = Math.abs(values[i1].approx - v);
  return d0 <= d1 ? i0 : i1;
}

function nearestLatticeXIndex(vIn: number): number {
  return nearestLatticeIndex(latticeXValues.value, clampWorldX(vIn));
}

function nearestLatticeYIndex(vIn: number): number {
  return nearestLatticeIndex(latticeYValues.value, clampWorldY(vIn));
}

function latticeValueAt(index: number, axis: "x" | "y"): LatticeValue {
  const values = axis === "x" ? latticeXValues.value : latticeYValues.value;
  if (values.length <= 0) {
    return { key: "0_0_0", exact: fromInt(0), approx: 0 };
  }
  const i = Math.max(0, Math.min(values.length - 1, index));
  return values[i];
}

function latticeXValueAt(index: number): LatticeValue {
  return latticeValueAt(index, "x");
}

function latticeYValueAt(index: number): LatticeValue {
  return latticeValueAt(index, "y");
}

function pointRadius(p: DesignerPoint): number {
  return Math.max(4, Math.min(12, 4 + p.size * 2));
}

function toCanvasX(u: number): number {
  return worldToCanvasUnitX(u) * CANVAS_SIZE;
}

function toCanvasY(v: number): number {
  return (1 - worldToCanvasUnitY(v)) * CANVAS_SIZE;
}

function normalizePoint(group: DesignerGroup, xIn: number, yIn: number): { x: number; y: number } {
  let ix = nearestLatticeXIndex(xIn);
  let iy = nearestLatticeYIndex(yIn);

  if (!symmetryEnabled.value || group === "free") {
    const xw = latticeXValueAt(ix).approx;
    const yw = latticeYValueAt(iy).approx;
    return {
      x: clampWorldX(xw),
      y: clampWorldY(yw),
    };
  }

  if (group === "axis") {
    const yByKey = new Set(latticeYValues.value.map((v) => v.key));
    let best: { x: number; y: number; score: number } | null = null;
    for (const xv of latticeXValues.value) {
      const yExact = add(sub(xv.exact, originOffsetExact.value.x), originOffsetExact.value.y);
      if (!yByKey.has(qsqrt2Key(yExact))) {
        continue;
      }
      const yApprox = qsqrt2Approx(yExact);
      const score = Math.hypot(xv.approx - xIn, yApprox - yIn);
      if (!best || score < best.score) {
        best = { x: xv.approx, y: yApprox, score };
      }
    }
    if (best) {
      return {
        x: clampWorldX(best.x),
        y: clampWorldY(best.y),
      };
    }
    const midLocal = (worldToLocalX(xIn) + worldToLocalY(yIn)) * 0.5;
    ix = nearestLatticeXIndex(localToWorldX(midLocal));
    iy = nearestLatticeYIndex(localToWorldY(midLocal));
  }

  let xw = latticeXValueAt(ix).approx;
  let yw = latticeYValueAt(iy).approx;
  if (group === "side" && worldToLocalX(xw) >= worldToLocalY(yw)) {
    const yValues = latticeYValues.value;
    if (iy + 1 < yValues.length) {
      iy += 1;
    } else if (ix > 0) {
      ix -= 1;
    }
    xw = latticeXValueAt(ix).approx;
    yw = latticeYValueAt(iy).approx;
    if (worldToLocalX(xw) >= worldToLocalY(yw)) {
      const midLocal = (worldToLocalX(xIn) + worldToLocalY(yIn)) * 0.5;
      const eps = Math.max(latticeStep.value, 1e-4);
      ix = nearestLatticeXIndex(localToWorldX(midLocal - eps));
      iy = nearestLatticeYIndex(localToWorldY(midLocal + eps));
      xw = latticeXValueAt(ix).approx;
      yw = latticeYValueAt(iy).approx;
    }
  }
  return {
    x: clampWorldX(xw),
    y: clampWorldY(yw),
  };
}

function getGroupPoints(group: DesignerGroup): DesignerPoint[] {
  if (group === "axis") {
    return axisPoints.value;
  }
  if (group === "side") {
    return sidePoints.value;
  }
  return freePoints.value;
}

function setGroupPoints(group: DesignerGroup, points: DesignerPoint[]): void {
  if (group === "axis") {
    axisPoints.value = points;
    return;
  }
  if (group === "side") {
    sidePoints.value = points;
    return;
  }
  freePoints.value = points;
}

function updatePoint(group: DesignerGroup, id: number, x: number, y: number): void {
  const pts = getGroupPoints(group);
  const idx = pts.findIndex((p) => p.id === id);
  if (idx < 0) {
    return;
  }
  const n = normalizePoint(group, x, y);
  const out = [...pts];
  out[idx] = { ...out[idx], x: n.x, y: n.y };
  setGroupPoints(group, out);
}

function updateSelectedSize(sizeIn: number): void {
  if (!selectedPoint.value) {
    return;
  }
  const pts = getGroupPoints(selectedPoint.value.group);
  const idx = pts.findIndex((p) => p.id === selectedPoint.value?.id);
  if (idx < 0) {
    return;
  }
  const size = Math.max(0.2, Math.min(3.0, Number.isFinite(sizeIn) ? sizeIn : 1));
  const out = [...pts];
  out[idx] = { ...out[idx], size };
  setGroupPoints(selectedPoint.value.group, out);
}

function pointerToNormInSvg(
  svg: SVGSVGElement | null,
  ev: PointerEvent | MouseEvent,
): { x: number; y: number } | null {
  if (!svg) {
    return null;
  }
  const ctm = svg.getScreenCTM();
  if (ctm) {
    try {
      const p = svg.createSVGPoint();
      p.x = ev.clientX;
      p.y = ev.clientY;
      const lp = p.matrixTransform(ctm.inverse());
      const xu = lp.x / CANVAS_SIZE;
      const yu = 1 - lp.y / CANVAS_SIZE;
      return { x: canvasUnitToWorldX(xu), y: canvasUnitToWorldY(yu) };
    } catch {
      // fall through to rect-based mapping
    }
  }
  const rect = svg.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    return null;
  }
  const xu = (ev.clientX - rect.left) / rect.width;
  const yu = 1 - (ev.clientY - rect.top) / rect.height;
  return { x: canvasUnitToWorldX(xu), y: canvasUnitToWorldY(yu) };
}

function pointerToNorm(ev: PointerEvent | MouseEvent): { x: number; y: number } | null {
  return pointerToNormInSvg(designerSvg.value, ev);
}

function addPointAt(x: number, y: number): void {
  const group: DesignerGroup = symmetryEnabled.value ? placementMode.value : "free";
  const n = normalizePoint(group, x, y);
  const p: DesignerPoint = {
    id: nextPointId.value++,
    x: n.x,
    y: n.y,
    size: 1,
  };
  setGroupPoints(group, [...getGroupPoints(group), p]);
  selectedPoint.value = { group, id: p.id };
}

function buildPickFromNorm(x: number, y: number): EdgePick {
  const vx = latticeXValueAt(nearestLatticeXIndex(x));
  const vy = latticeYValueAt(nearestLatticeYIndex(y));
  const point: PointE = {
    x: vx.exact,
    y: vy.exact,
  };
  const key = pointExactKey(point);
  return {
    key,
    point,
    x: clampWorldX(vx.approx),
    y: clampWorldY(vy.approx),
    cornerIdx: activeCornerIndexByExactKey.value.get(key) ?? null,
  };
}

function buildPickFromCornerIndex(idx: number): EdgePick | null {
  if (idx < 0 || idx >= activeCorners.value.length) {
    return null;
  }
  const point = activeCorners.value[idx];
  return {
    key: pointExactKey(point),
    point,
    x: clampWorldX(qsqrt2Approx(point.x)),
    y: clampWorldY(qsqrt2Approx(point.y)),
    cornerIdx: idx,
  };
}

function findNearestActiveCornerIndex(
  x: number,
  y: number,
  threshold = 0.035,
): number | null {
  let bestIdx: number | null = null;
  let bestDist = Number.POSITIVE_INFINITY;
  for (const c of activeCornerCanvasPoints.value) {
    const dx = c.x - x;
    const dy = c.y - y;
    const d = Math.hypot(dx, dy);
    if (d < bestDist) {
      bestDist = d;
      bestIdx = c.idx;
    }
  }
  return bestDist <= threshold ? bestIdx : null;
}

function onCanvasClick(ev: MouseEvent): void {
  if (canvasEditMode.value === "edge") {
    return;
  }
  const target = ev.target as HTMLElement | null;
  if (target?.dataset.cornerId) {
    return;
  }
  const pt = pointerToNorm(ev);
  if (!pt) {
    return;
  }
  addPointAt(pt.x, pt.y);
}

function onPointPointerDown(group: DesignerGroup, id: number, ev: PointerEvent): void {
  if (canvasEditMode.value === "edge") {
    return;
  }
  ev.preventDefault();
  selectedPoint.value = { group, id };
  dragState.value = { group, id };
}

function onCanvasPointerDown(ev: PointerEvent): void {
  if (canvasEditMode.value !== "edge") {
    return;
  }
  const target = ev.target as HTMLElement | null;
  if (target?.dataset.activeCornerIdx) {
    return;
  }
  const pt = pointerToNorm(ev);
  if (!pt) {
    return;
  }
  const pick = buildPickFromNorm(pt.x, pt.y);
  edgeDragStartPick.value = pick;
  edgeDragMoved.value = false;
  edgeDraftPointer.value = { x: pick.x, y: pick.y };
}

function onActiveCornerPointerDown(idx: number, ev: PointerEvent): void {
  if (canvasEditMode.value !== "edge") {
    return;
  }
  ev.preventDefault();
  ev.stopPropagation();
  const pick = buildPickFromCornerIndex(idx);
  if (!pick) {
    return;
  }
  edgeDragStartPick.value = pick;
  edgeDragMoved.value = false;
  edgeDraftPointer.value = { x: pick.x, y: pick.y };
}

function onCanvasPointerMove(ev: PointerEvent): void {
  if (canvasEditMode.value === "edge") {
    const pt = pointerToNorm(ev);
    if (!pt) {
      return;
    }
    if (edgeDraftStartPick.value !== null) {
      edgeDraftPointer.value = { x: pt.x, y: pt.y };
    }
    if (edgeDragStartPick.value !== null) {
      const p0 = edgeDragStartPick.value;
      if (p0 && Math.hypot(pt.x - p0.x, pt.y - p0.y) > 0.006) {
        edgeDragMoved.value = true;
        edgeDraftPointer.value = { x: pt.x, y: pt.y };
      }
    }
    return;
  }
  if (!dragState.value) {
    return;
  }
  const pt = pointerToNorm(ev);
  if (!pt) {
    return;
  }
  updatePoint(dragState.value.group, dragState.value.id, pt.x, pt.y);
}

function onCanvasPointerUp(ev?: PointerEvent): void {
  if (canvasEditMode.value === "edge") {
    if (edgeDragStartPick.value === null) {
      return;
    }
    const start = edgeDragStartPick.value;
    const pt = ev ? pointerToNorm(ev) : null;
    const hitIdx = pt ? findNearestActiveCornerIndex(pt.x, pt.y) : null;
    const endPick =
      hitIdx !== null ? buildPickFromCornerIndex(hitIdx) : pt ? buildPickFromNorm(pt.x, pt.y) : null;

    if (edgeDragMoved.value) {
      if (endPick && endPick.key !== start.key) {
        addSeedEdgeByPicks(start, endPick);
      }
      edgeDraftStartPick.value = null;
      edgeDraftPointer.value = null;
    } else if (edgeDraftStartPick.value === null) {
      edgeDraftStartPick.value = start;
      edgeDraftPointer.value = { x: start.x, y: start.y };
    } else if (edgeDraftStartPick.value.key === start.key) {
      edgeDraftStartPick.value = null;
      edgeDraftPointer.value = null;
    } else {
      addSeedEdgeByPicks(edgeDraftStartPick.value, start);
      edgeDraftStartPick.value = null;
      edgeDraftPointer.value = null;
    }
    edgeDragStartPick.value = null;
    edgeDragMoved.value = false;
    return;
  }
  dragState.value = null;
}

function deleteSelectedPoint(): void {
  if (!selectedPoint.value) {
    return;
  }
  const pts = getGroupPoints(selectedPoint.value.group);
  setGroupPoints(
    selectedPoint.value.group,
    pts.filter((p) => p.id !== selectedPoint.value?.id),
  );
  selectedPoint.value = null;
}

function clearDesignerInteriorPoints(): void {
  axisPoints.value = [];
  sidePoints.value = [];
  freePoints.value = [];
  selectedPoint.value = null;
}

function resetDesignerDefaults(): void {
  axisPoints.value = [{ id: nextPointId.value++, x: 0, y: 0, size: 1 }];
  sidePoints.value = [];
  freePoints.value = [{ id: nextPointId.value++, x: 0, y: 0, size: 1 }];
  selectedPoint.value = null;
}

function loadSampleLayoutBasic(): void {
  const axisLocal = [-0.22, 0.06];
  const sideLocal: Array<[number, number]> = [
    [-0.28, -0.05],
    [-0.16, 0.14],
    [0.02, 0.26],
  ];
  const freeLocal: Array<[number, number]> = [
    [-0.28, -0.18],
    [-0.12, 0.08],
    [0.18, -0.12],
    [0.24, 0.24],
  ];

  if (symmetryEnabled.value) {
    axisPoints.value = axisLocal.map((t) => {
      const n = normalizePoint("axis", localToWorldX(t), localToWorldY(t));
      return { id: nextPointId.value++, x: n.x, y: n.y, size: 1 };
    });
    sidePoints.value = sideLocal.map(([x, y]) => {
      const n = normalizePoint("side", localToWorldX(x), localToWorldY(y));
      return { id: nextPointId.value++, x: n.x, y: n.y, size: 1 };
    });
    freePoints.value = [];
  } else {
    axisPoints.value = [];
    sidePoints.value = [];
    freePoints.value = freeLocal.map(([x, y]) => {
      const n = normalizePoint("free", localToWorldX(x), localToWorldY(y));
      return { id: nextPointId.value++, x: n.x, y: n.y, size: 1 };
    });
  }
  seedEdges.value = [];
  seedSegments.value = [];
  selectedPoint.value = null;
  errorMessage.value = "";
}

function resnapDesignerPointsToLattice(): void {
  axisPoints.value = axisPoints.value.map((p) => {
    const n = normalizePoint("axis", p.x, p.y);
    return { ...p, x: n.x, y: n.y };
  });
  sidePoints.value = sidePoints.value.map((p) => {
    const n = normalizePoint("side", p.x, p.y);
    return { ...p, x: n.x, y: n.y };
  });
  freePoints.value = freePoints.value.map((p) => {
    const n = normalizePoint("free", p.x, p.y);
    return { ...p, x: n.x, y: n.y };
  });
}

const selectedMeta = computed(() => {
  if (!selectedPoint.value) {
    return null;
  }
  const pts = getGroupPoints(selectedPoint.value.group);
  const point = pts.find((p) => p.id === selectedPoint.value?.id);
  if (!point) {
    return null;
  }
  return { group: selectedPoint.value.group, point };
});

const selectedPointExact = computed<{ x: Qsqrt2; y: Qsqrt2 } | null>(() => {
  if (!selectedMeta.value) {
    return null;
  }
  const p = selectedMeta.value.point;
  const xExact = latticeXValueAt(nearestLatticeXIndex(p.x)).exact;
  const yExact = latticeYValueAt(nearestLatticeYIndex(p.y)).exact;
  return { x: xExact, y: yExact };
});

function updateSelectedCoordExact(axis: "x" | "y", part: "a" | "b" | "k", raw: string): void {
  if (!selectedMeta.value || !selectedPointExact.value) {
    return;
  }
  const v = Number(raw);
  if (!Number.isFinite(v)) {
    return;
  }
  const current = axis === "x" ? selectedPointExact.value.x : selectedPointExact.value.y;
  const a0 = Number(current.a);
  const b0 = Number(current.b);
  const k0 = current.k;
  const a = part === "a" ? Math.trunc(v) : a0;
  const b = part === "b" ? Math.trunc(v) : b0;
  const k = part === "k" ? clampInt(v, 0, 16) : k0;
  const z = qsqrt2(a, b, k);
  const x = axis === "x" ? qsqrt2Approx(z) : selectedMeta.value.point.x;
  const y = axis === "y" ? qsqrt2Approx(z) : selectedMeta.value.point.y;
  updatePoint(selectedMeta.value.group, selectedMeta.value.point.id, x, y);
}

const designerGridDots = computed(() => {
  if (!showDesignerGrid.value) {
    return [] as Array<{ x: number; y: number; key: string }>;
  }
  const xValues = latticeXValues.value;
  const yValues = latticeYValues.value;
  if (xValues.length <= 0 || yValues.length <= 0) {
    return [] as Array<{ x: number; y: number; key: string }>;
  }
  const nx = xValues.length;
  const ny = yValues.length;
  const total = nx * ny;
  const maxDots = 2400;
  const stride = Math.max(1, Math.ceil(Math.sqrt(total / maxDots)));
  const out: Array<{ x: number; y: number; key: string }> = [];
  const seen = new Set<string>();
  function add(ix: number, iy: number): void {
    const key = `${ix}_${iy}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    out.push({
      x: clampWorldX(xValues[ix].approx),
      y: clampWorldY(yValues[iy].approx),
      key,
    });
  }
  for (let ix = 0; ix < nx; ix += stride) {
    for (let iy = 0; iy < ny; iy += stride) {
      add(ix, iy);
    }
  }
  for (let ix = 0; ix < nx; ix += stride) {
    add(ix, ny - 1);
  }
  for (let iy = 0; iy < ny; iy += stride) {
    add(nx - 1, iy);
  }
  add(0, 0);
  add(0, ny - 1);
  add(nx - 1, 0);
  add(nx - 1, ny - 1);
  return out;
});

const symmetryAxisLine = computed<null | { x1: number; y1: number; x2: number; y2: number }>(() => {
  if (!symmetryEnabled.value) {
    return null;
  }
  const b = paperWindow.value;
  const c = originOffsetApprox.value.y - originOffsetApprox.value.x;
  const pts: Array<{ x: number; y: number }> = [];
  const seen = new Set<string>();

  function addPt(x: number, y: number): void {
    if (x < b.xMin - 1e-10 || x > b.xMax + 1e-10 || y < b.yMin - 1e-10 || y > b.yMax + 1e-10) {
      return;
    }
    const key = `${Math.round(x * 1e9)},${Math.round(y * 1e9)}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    pts.push({ x, y });
  }

  addPt(b.xMin, b.xMin + c);
  addPt(b.xMax, b.xMax + c);
  addPt(b.yMin - c, b.yMin);
  addPt(b.yMax - c, b.yMax);

  if (pts.length < 2) {
    return null;
  }
  let bestI = 0;
  let bestJ = 1;
  let bestD2 = -1;
  for (let i = 0; i < pts.length; i += 1) {
    for (let j = i + 1; j < pts.length; j += 1) {
      const dx = pts[i].x - pts[j].x;
      const dy = pts[i].y - pts[j].y;
      const d2 = dx * dx + dy * dy;
      if (d2 > bestD2) {
        bestD2 = d2;
        bestI = i;
        bestJ = j;
      }
    }
  }
  return {
    x1: pts[bestI].x,
    y1: pts[bestI].y,
    x2: pts[bestJ].x,
    y2: pts[bestJ].y,
  };
});

const mirroredSidePoints = computed(() =>
  sidePoints.value.map((p) => {
    const m = mirrorApproxByLocalDiag(p.x, p.y);
    return {
      id: p.id,
      x: clampWorldX(m.x),
      y: clampWorldY(m.y),
      size: p.size,
    };
  }),
);

const designerCorners = computed<PointE[]>(() => {
  const coords = new Map<string, PointE>();

  function addXY(x: number, y: number): void {
    const px = latticeXValueAt(nearestLatticeXIndex(x)).exact;
    const py = latticeYValueAt(nearestLatticeYIndex(y)).exact;
    const p: PointE = { x: px, y: py };
    coords.set(pointExactKey(p), p);
  }

  addXY(paperWindow.value.xMin, paperWindow.value.yMin);
  addXY(paperWindow.value.xMin, paperWindow.value.yMax);
  addXY(paperWindow.value.xMax, paperWindow.value.yMin);
  addXY(paperWindow.value.xMax, paperWindow.value.yMax);

  if (symmetryEnabled.value) {
    for (const p of axisPoints.value) {
      addXY(p.x, p.y);
    }
    for (const p of sidePoints.value) {
      addXY(p.x, p.y);
      const mp = mirrorApproxByLocalDiag(p.x, p.y);
      addXY(mp.x, mp.y);
    }
  } else {
    for (const p of freePoints.value) {
      addXY(p.x, p.y);
    }
  }

  return [...coords.values()].sort((lhs, rhs) => {
    const dx = qsqrt2Approx(lhs.x) - qsqrt2Approx(rhs.x);
    if (Math.abs(dx) > 1e-12) {
      return dx;
    }
    const dy = qsqrt2Approx(lhs.y) - qsqrt2Approx(rhs.y);
    if (Math.abs(dy) > 1e-12) {
      return dy;
    }
    return pointExactKey(lhs).localeCompare(pointExactKey(rhs));
  });
});

const activeCorners = computed<PointE[]>(() => designerCorners.value);

const activeCornerIndexByExactKey = computed(() => {
  const out = new Map<string, number>();
  for (let i = 0; i < activeCorners.value.length; i += 1) {
    out.set(pointExactKey(activeCorners.value[i]), i);
  }
  return out;
});

const activeCornerCanvasPoints = computed(() =>
  activeCorners.value.map((p, idx) => ({
    idx,
    x: clampWorldX(qsqrt2Approx(p.x)),
    y: clampWorldY(qsqrt2Approx(p.y)),
  })),
);

const activeCornerCanvasByIdx = computed(() => {
  const m = new Map<number, { x: number; y: number }>();
  for (const c of activeCornerCanvasPoints.value) {
    m.set(c.idx, { x: c.x, y: c.y });
  }
  return m;
});

const seedEdgeCanvasLines = computed(() => {
  const byIdx = activeCornerCanvasByIdx.value;
  const lines: Array<{ key: string; x1: number; y1: number; x2: number; y2: number }> = [];
  for (const e of seedEdges.value) {
    const p0 = byIdx.get(e.cornerI);
    const p1 = byIdx.get(e.cornerJ);
    if (!p0 || !p1) {
      continue;
    }
    lines.push({
      key: `${e.cornerI}_${e.cornerJ}`,
      x1: p0.x,
      y1: p0.y,
      x2: p1.x,
      y2: p1.y,
    });
  }
  return lines;
});

const seedSegmentCanvasLines = computed(() =>
  seedSegments.value.map((seg, idx) => ({
    key: `seg_${idx}`,
    x1: clampWorldX(qsqrt2Approx(seg.from.x)),
    y1: clampWorldY(qsqrt2Approx(seg.from.y)),
    x2: clampWorldX(qsqrt2Approx(seg.to.x)),
    y2: clampWorldY(qsqrt2Approx(seg.to.y)),
  })),
);

const edgeDraftLine = computed<null | { x1: number; y1: number; x2: number; y2: number }>(() => {
  if (canvasEditMode.value !== "edge") {
    return null;
  }
  if (!edgeDraftPointer.value) {
    return null;
  }
  const start = edgeDraftStartPick.value ?? edgeDragStartPick.value;
  if (!start) {
    return null;
  }
  const p0 = { x: start.x, y: start.y };
  if (!p0) {
    return null;
  }
  return {
    x1: p0.x,
    y1: p0.y,
    x2: edgeDraftPointer.value.x,
    y2: edgeDraftPointer.value.y,
  };
});


const selectedEvaluation = computed<CreasegenProfileEvaluation | null>(() => {
  if (evaluations.value.length <= 0) {
    return null;
  }
  if (selectedProfileName.value) {
    const found = evaluations.value.find((ev) => ev.profile.name === selectedProfileName.value);
    if (found) {
      return found;
    }
  }
  if (bestProfileName.value) {
    const best = evaluations.value.find((ev) => ev.profile.name === bestProfileName.value);
    if (best) {
      return best;
    }
  }
  return evaluations.value[0];
});

const selectedGraph = computed<CreaseGraphMem | null>(() => selectedEvaluation.value?.result.graph ?? null);

const cpViewData = computed(() => {
  const graph = selectedGraph.value;
  if (!graph) {
    return null;
  }
  const vertices = new Map<number, CreaseGraphMem["vertices"][number]>();
  for (const v of graph.vertices) {
    vertices.set(v.id, v);
  }

  const edgeLines: Array<{ x1: number; y1: number; x2: number; y2: number; boundary: boolean }> = [];
  for (const e of graph.edges) {
    const v0 = vertices.get(e.v0);
    const v1 = vertices.get(e.v1);
    if (!v0 || !v1) {
      continue;
    }
    edgeLines.push({
      x1: worldToCanvasUnitX(v0.pointApprox.x) * CP_VIEW_SIZE,
      y1: (1 - worldToCanvasUnitY(v0.pointApprox.y)) * CP_VIEW_SIZE,
      x2: worldToCanvasUnitX(v1.pointApprox.x) * CP_VIEW_SIZE,
      y2: (1 - worldToCanvasUnitY(v1.pointApprox.y)) * CP_VIEW_SIZE,
      boundary: e.isBoundary,
    });
  }

  const cornerIds = new Set<number>(graph.corners);
  const pointMarks = graph.vertices.map((v) => ({
    id: v.id,
    x: worldToCanvasUnitX(v.pointApprox.x) * CP_VIEW_SIZE,
    y: (1 - worldToCanvasUnitY(v.pointApprox.y)) * CP_VIEW_SIZE,
    corner: cornerIds.has(v.id),
    boundary: v.isBoundary,
  }));

  return {
    edgeLines,
    pointMarks,
    stats: graph.stats,
  };
});

const foldViewData = computed(() => {
  const preview = previewResult.value;
  if (!preview || preview.facePolygons.length <= 0) {
    return null;
  }

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let minDepth = Number.POSITIVE_INFINITY;
  let maxDepth = Number.NEGATIVE_INFINITY;
  for (const face of preview.facePolygons) {
    minDepth = Math.min(minDepth, face.depth);
    maxDepth = Math.max(maxDepth, face.depth);
    for (const p of face.points) {
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null;
  }

  const pad = 16;
  const w = Math.max(1e-9, maxX - minX);
  const h = Math.max(1e-9, maxY - minY);
  const scale = Math.min((FOLD_VIEW_SIZE - pad * 2) / w, (FOLD_VIEW_SIZE - pad * 2) / h);
  const ox = pad + (FOLD_VIEW_SIZE - pad * 2 - w * scale) * 0.5;
  const oy = pad + (FOLD_VIEW_SIZE - pad * 2 - h * scale) * 0.5;

  const faces = preview.facePolygons.map((face) => {
    const mapped = face.points.map((p) => ({
      x: ox + (p.x - minX) * scale,
      y: oy + (maxY - p.y) * scale,
    }));
    const pointsAttr = mapped.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ");
    const cx = mapped.reduce((acc, p) => acc + p.x, 0) / Math.max(1, mapped.length);
    const cy = mapped.reduce((acc, p) => acc + p.y, 0) / Math.max(1, mapped.length);
    return {
      faceId: face.faceId,
      depth: face.depth,
      fill: foldFaceFill(face.depth, minDepth, maxDepth),
      fillOpacity: foldFaceOpacity(face.depth, minDepth, maxDepth),
      pointsAttr,
      cx,
      cy,
    };
  });

  return {
    faces,
    stats: preview.stats,
  };
});

function centeredWorldDomainFromWindow(): CpGraphV1Json["domain"] {
  return {
    shape: "unit_square",
    x_min: paperWindow.value.xMin,
    x_max: paperWindow.value.xMax,
    y_min: paperWindow.value.yMin,
    y_max: paperWindow.value.yMax,
  };
}

function legacyUnitDomain(): CpGraphV1Json["domain"] {
  return {
    shape: "unit_square",
    x_min: 0.0,
    x_max: 1.0,
    y_min: 0.0,
    y_max: 1.0,
  };
}

function toLegacyPointExact(p: PointE): PointE {
  const half = fromDyadic(1, 1);
  return {
    x: add(sub(p.x, originOffsetExact.value.x), half),
    y: add(sub(p.y, originOffsetExact.value.y), half),
  };
}

function toLegacyApprox(xWorld: number, yWorld: number): { x: number; y: number } {
  return {
    x: xWorld - originOffsetApprox.value.x + 0.5,
    y: yWorld - originOffsetApprox.value.y + 0.5,
  };
}

function graphWorldToLegacyUnit(graph: CreaseGraphMem): CreaseGraphMem {
  return {
    ...graph,
    vertices: graph.vertices.map((v) => {
      const p = toLegacyPointExact(v.point);
      const pa = toLegacyApprox(v.pointApprox.x, v.pointApprox.y);
      return {
        ...v,
        point: p,
        pointApprox: { x: pa.x, y: pa.y },
      };
    }),
  };
}

function formatCpNumber(vIn: number): string {
  if (!Number.isFinite(vIn)) {
    return "0";
  }
  const v = Math.abs(vIn) < 1e-12 ? 0 : vIn;
  return v.toFixed(10).replace(/\.?0+$/, "");
}

function toOripaCpText(
  graph: CreaseGraphMem,
  domain: CpGraphV1Json["domain"],
): string {
  const byId = new Map<number, CreaseGraphMem["vertices"][number]>();
  for (const v of graph.vertices) {
    byId.set(v.id, v);
  }

  const yMid = domain.y_min + domain.y_max;
  const lines: string[] = [];
  for (const e of graph.edges) {
    const v0 = byId.get(e.v0);
    const v1 = byId.get(e.v1);
    if (!v0 || !v1) {
      continue;
    }
    // ORIPA CP line-type:
    // 0=aux, 1=cut(boundary), 2=ridge(mountain), 3=valley
    // This graph currently has no explicit mountain/valley assignment.
    const lineType = e.isBoundary ? 1 : 2;
    // ORIPA CP assumes y axis downward; convert from internal y-up world/legacy frame.
    const x0 = v0.pointApprox.x;
    const y0 = yMid - v0.pointApprox.y;
    const x1 = v1.pointApprox.x;
    const y1 = yMid - v1.pointApprox.y;
    lines.push(
      `${lineType} ${formatCpNumber(x0)} ${formatCpNumber(y0)} ${formatCpNumber(x1)} ${formatCpNumber(y1)}`,
    );
  }
  return `${lines.join("\n")}\n`;
}

function exportSelectedOripaCp(): void {
  const graph = selectedGraph.value;
  if (!graph) {
    errorMessage.value = "no generated crease graph to export";
    return;
  }

  const legacy = cpGraphExportPolicy.value === "legacy_unit";
  const outGraph = legacy ? graphWorldToLegacyUnit(graph) : graph;
  const domain = legacy ? legacyUnitDomain() : centeredWorldDomainFromWindow();
  const cpText = toOripaCpText(outGraph, domain);

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const tag = legacy ? "legacy01" : "centered";
  const filename = `oripa_cp_${tag}_${stamp}.cp`;

  const blob = new Blob([cpText], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  errorMessage.value = "";
}

function exportSelectedCpGraph(): void {
  const graph = selectedGraph.value;
  if (!graph) {
    errorMessage.value = "no generated crease graph to export";
    return;
  }

  const legacy = cpGraphExportPolicy.value === "legacy_unit";
  const outGraph = legacy ? graphWorldToLegacyUnit(graph) : graph;
  const domain = legacy ? legacyUnitDomain() : centeredWorldDomainFromWindow();
  const payload = memGraphToCpGraphV1(outGraph, { domain });
  const json = JSON.stringify(payload, null, 2);

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const tag = legacy ? "legacy01" : "centered";
  const filename = `cp_graph_v1_${tag}_${stamp}.json`;

  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  errorMessage.value = "";
}

const mirrorIndexByCorner = computed(() => {
  const byKey = new Map<string, number>();
  for (let i = 0; i < activeCorners.value.length; i += 1) {
    byKey.set(pointExactKey(activeCorners.value[i]), i);
  }
  const out = new Map<number, number>();
  for (let i = 0; i < activeCorners.value.length; i += 1) {
    const mirrored = byKey.get(mirroredPointExactKey(activeCorners.value[i]));
    if (mirrored !== undefined) {
      out.set(i, mirrored);
    }
  }
  return out;
});

const seedEdgesForRun = computed<CreaseSeedEdgeInput[]>(() => {
  const count = activeCorners.value.length;
  const seen = new Set<string>();
  const out: CreaseSeedEdgeInput[] = [];

  function pushPair(i: number, j: number): void {
    const n = normalizeSeedEdgePair(i, j, count);
    if (!n) {
      return;
    }
    const key = `${n.cornerI},${n.cornerJ}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    out.push(n);
  }

  for (const e of seedEdges.value) {
    pushPair(e.cornerI, e.cornerJ);
  }

  if (symmetryEnabled.value && seedEdgeAutoMirror.value) {
    for (const e of seedEdges.value) {
      const mi = mirrorIndexByCorner.value.get(e.cornerI);
      const mj = mirrorIndexByCorner.value.get(e.cornerJ);
      if (mi === undefined || mj === undefined) {
        continue;
      }
      pushPair(mi, mj);
    }
  }

  return out;
});

const seedEdgeAutoAddedCount = computed(
  () => Math.max(0, seedEdgesForRun.value.length - seedEdges.value.length),
);

function normalizedSeedSegment(seg: CreaseSeedSegmentInput): CreaseSeedSegmentInput | null {
  const fromKey = pointExactKey(seg.from);
  const toKey = pointExactKey(seg.to);
  if (fromKey === toKey) {
    return null;
  }
  return fromKey <= toKey ? seg : { from: seg.to, to: seg.from };
}

function seedSegmentKey(seg: CreaseSeedSegmentInput): string {
  return `${pointExactKey(seg.from)}|${pointExactKey(seg.to)}`;
}

function mirrorSeedSegmentYEqX(seg: CreaseSeedSegmentInput): CreaseSeedSegmentInput {
  return {
    from: mirrorPointExactByLocalDiag(seg.from),
    to: mirrorPointExactByLocalDiag(seg.to),
  };
}

const seedSegmentsForRun = computed<CreaseSeedSegmentInput[]>(() => {
  const seen = new Set<string>();
  const out: CreaseSeedSegmentInput[] = [];

  function push(seg: CreaseSeedSegmentInput): void {
    const n = normalizedSeedSegment(seg);
    if (!n) {
      return;
    }
    const key = seedSegmentKey(n);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    out.push(n);
  }

  for (const seg of seedSegments.value) {
    push(seg);
  }

  if (symmetryEnabled.value && seedSegmentAutoMirror.value) {
    for (const seg of seedSegments.value) {
      push(mirrorSeedSegmentYEqX(seg));
    }
  }

  return out;
});

const seedSegmentAutoAddedCount = computed(
  () => Math.max(0, seedSegmentsForRun.value.length - seedSegments.value.length),
);

function addSeedSegmentExact(from: PointE, to: PointE): boolean {
  const n = normalizedSeedSegment({ from, to });
  if (!n) {
    errorMessage.value = "invalid seed segment: from and to must be different points";
    return false;
  }
  const key = seedSegmentKey(n);
  if (seedSegments.value.some((s) => seedSegmentKey(normalizedSeedSegment(s) ?? s) === key)) {
    return false;
  }
  errorMessage.value = "";
  seedSegments.value = [...seedSegments.value, n];
  return true;
}

function clearSeedSegments(): void {
  seedSegments.value = [];
}

function sanitizeSeedEdges(): void {
  const count = activeCorners.value.length;
  const seen = new Set<string>();
  const out: CreaseSeedEdgeInput[] = [];
  for (const e of seedEdges.value) {
    const n = normalizeSeedEdgePair(e.cornerI, e.cornerJ, count);
    if (!n) {
      continue;
    }
    const key = `${n.cornerI},${n.cornerJ}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(n);
  }
  seedEdges.value = out;
}

function addSeedEdgeByCornerIndices(i: number, j: number): boolean {
  const n = normalizeSeedEdgePair(i, j, activeCorners.value.length);
  if (!n) {
    errorMessage.value = "invalid seed edge: choose two different corner indices";
    return false;
  }
  const key = `${n.cornerI},${n.cornerJ}`;
  if (seedEdges.value.some((e) => `${e.cornerI},${e.cornerJ}` === key)) {
    return false;
  }
  errorMessage.value = "";
  seedEdges.value = [...seedEdges.value, n];
  return true;
}

function addSeedEdgeByPicks(from: EdgePick, to: EdgePick): boolean {
  if (from.key === to.key) {
    return false;
  }
  if (from.cornerIdx !== null && to.cornerIdx !== null) {
    return addSeedEdgeByCornerIndices(from.cornerIdx, to.cornerIdx);
  }
  return addSeedSegmentExact(from.point, to.point);
}

function clearSeedEdges(): void {
  seedEdges.value = [];
  edgeDraftStartPick.value = null;
  edgeDraftPointer.value = null;
}

watch(activeCorners, () => {
  sanitizeSeedEdges();
});
sanitizeSeedEdges();
watch([aMaxInput, bMaxInput, kMaxInput], () => {
  resnapDesignerPointsToLattice();
});
watch(
  originOffsetExact,
  (next, prev) => {
    if (!prev) {
      return;
    }
    if (q2Cmp(next.x, prev.x) === 0 && q2Cmp(next.y, prev.y) === 0) {
      return;
    }
    edgeDraftStartPick.value = null;
    edgeDraftPointer.value = null;
    edgeDragStartPick.value = null;
    edgeDragMoved.value = false;
  },
  { deep: false },
);
watch(canvasEditMode, () => {
  edgeDraftStartPick.value = null;
  edgeDraftPointer.value = null;
  edgeDragStartPick.value = null;
  edgeDragMoved.value = false;
});

function buildTilingInputFromDesigner(): TilingRunInput {
  if (!symmetryEnabled.value) {
    throw new Error("tiling stage currently expects local y=x symmetry mode to be ON");
  }

  const specs: KadoSpec[] = [];
  const initialCenters: Record<string, Vec2> = {};
  for (const p of axisPoints.value) {
    const name = `axis_${p.id}`;
    specs.push({
      name,
      length: p.size,
      symmetry: "axis",
    });
    initialCenters[name] = { x: p.x, y: p.y };
  }
  for (const p of sidePoints.value) {
    const l = `pair_${p.id}_l`;
    const r = `pair_${p.id}_r`;
    specs.push({ name: l, length: p.size, symmetry: "pair", pairName: r });
    specs.push({ name: r, length: p.size, symmetry: "pair", pairName: l });
    initialCenters[l] = { x: p.x, y: p.y };
    const mp = mirrorApproxByLocalDiag(p.x, p.y);
    initialCenters[r] = { x: mp.x, y: mp.y };
  }

  if (specs.length <= 0) {
    throw new Error("no interior kado points to optimize; add axis or side points first");
  }

  return {
    specs,
    originOffset: originOffsetExact.value,
    lattice: tilingLatticeConfig.value,
    seed: clampInt(tilingSeed.value, -2147483648, 2147483647),
    alphaSteps: clampInt(tilingAlphaSteps.value, 1, 64),
    packRestarts: clampInt(tilingPackRestarts.value, 1, 200),
    packIters: clampInt(tilingPackIters.value, 1, 5000),
    warmStart: true,
    initialCenters,
  };
}

function replaceDesignerPointsWithTiling(tiling: TilingState): void {
  const sizeByName = new Map<string, number>();
  for (const p of axisPoints.value) {
    sizeByName.set(`axis_${p.id}`, p.size);
  }
  for (const p of sidePoints.value) {
    sizeByName.set(`pair_${p.id}_l`, p.size);
  }

  const nextAxis: DesignerPoint[] = [];
  const nextSide: DesignerPoint[] = [];
  const centers = tiling.centers;
  const sideTol = 1e-10;
  const isLocalSideHalf = (v: Vec2): boolean => worldToLocalX(v.x) < worldToLocalY(v.y) - sideTol;
  const toPairRName = (pairLName: string): string =>
    pairLName.endsWith("_l") ? `${pairLName.slice(0, -2)}_r` : `${pairLName}_r`;

  const entries = Object.entries(tiling.centers).sort(([ka], [kb]) => ka.localeCompare(kb));
  for (const [name, center] of entries) {
    if (name.startsWith("axis_")) {
      const n = normalizePoint("axis", center.x, center.y);
      nextAxis.push({
        id: nextPointId.value++,
        x: n.x,
        y: n.y,
        size: sizeByName.get(name) ?? 1,
      });
      continue;
    }
    if (name.startsWith("pair_") && name.endsWith("_l")) {
      const pairRCenter = centers[toPairRName(name)];
      let sideCenter = center;
      if (!isLocalSideHalf(sideCenter)) {
        if (pairRCenter && isLocalSideHalf(pairRCenter)) {
          sideCenter = pairRCenter;
        } else if (pairRCenter) {
          sideCenter = pairRCenter;
        } else {
          sideCenter = mirrorApproxByLocalDiag(center.x, center.y);
        }
      }
      const n = normalizePoint("side", sideCenter.x, sideCenter.y);
      nextSide.push({
        id: nextPointId.value++,
        x: n.x,
        y: n.y,
        size: sizeByName.get(name) ?? 1,
      });
    }
  }

  axisPoints.value = nextAxis;
  sidePoints.value = nextSide;
  freePoints.value = [];
  selectedPoint.value = null;
}

const offProgress = engine.onProgress((ev) => {
  progressRatio.value = ev.ratio;
  progressStage.value = ev.stage;
  progressMessage.value = ev.message ?? "";
});

async function runTilingFromDesigner(): Promise<void> {
  busy.value = true;
  errorMessage.value = "";
  progressRatio.value = 0;
  progressStage.value = "tiling";
  progressMessage.value = "tiling start";
  try {
    const input = buildTilingInputFromDesigner();
    const out = await engine.runTiling(input);
    tilingState.value = out;
    if (!out.ok) {
      errorMessage.value = `tiling failed: ${out.message}`;
      return;
    }
    replaceDesignerPointsWithTiling(out);
    evaluations.value = [];
    bestProfileName.value = "";
    selectedProfileName.value = "";
    previewResult.value = null;
    previewProfileName.value = "";
    progressMessage.value = "tiling done";
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

function selectProfileForPreview(profileName: string): void {
  selectedProfileName.value = profileName;
}

async function runPreviewForGraph(graph: CreaseGraphMem | null, profileName?: string): Promise<void> {
  if (!graph) {
    previewResult.value = null;
    previewProfileName.value = "";
    return;
  }
  busy.value = true;
  errorMessage.value = "";
  progressRatio.value = 0;
  progressStage.value = "preview";
  progressMessage.value = "preview start";
  try {
    const out = await engine.runPreview({
      graph,
      alpha: previewAlpha.value,
      lineWidth: previewLineWidth.value,
      showFaceId: previewShowFaceId.value,
    });
    previewResult.value = out;
    previewProfileName.value = profileName ?? selectedProfileName.value;
    progressMessage.value = "preview done";
  } catch (err) {
    previewResult.value = null;
    previewProfileName.value = "";
    errorMessage.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function runPreviewForSelectedProfile(): Promise<void> {
  await runPreviewForGraph(
    selectedEvaluation.value?.result.graph ?? null,
    selectedEvaluation.value?.profile.name ?? "",
  );
}

async function runProfiles(): Promise<void> {
  busy.value = true;
  errorMessage.value = "";
  evaluations.value = [];
  bestProfileName.value = "";
  selectedProfileName.value = "";
  previewResult.value = null;
  previewProfileName.value = "";
  progressRatio.value = 0;
  progressStage.value = "creasegen";
  progressMessage.value = "starting";
  try {
    const out = await engine.runCreasegenProfiles({
      corners: activeCorners.value,
      originOffset: originOffsetExact.value,
      seedEdges: seedEdgesForRun.value.length > 0 ? seedEdgesForRun.value : undefined,
      seedSegments: seedSegmentsForRun.value.length > 0 ? seedSegmentsForRun.value : undefined,
      tiling: tilingState.value ?? undefined,
      profiles: DEFAULT_REAL_DATA_EVAL_PROFILES,
      baseConfig: {
        aMax: clampInt(aMaxInput.value, 1, 24),
        bMax: clampInt(bMaxInput.value, 1, 24),
        kMax: clampInt(kMaxInput.value, 1, 8),
        maxDepth: clampInt(searchMaxDepthInput.value, 1, 64),
        branchPerNode: clampInt(searchBranchPerNodeInput.value, 1, 64),
        maxNodes: clampInt(searchMaxNodesInput.value, 1, 200000),
        allowViolations: clampInt(searchAllowViolationsInput.value, 0, 64),
        dirTopK: clampInt(searchDirTopKInput.value, 1, 16),
        priorityTopN: clampInt(searchPriorityTopNInput.value, 1, 32),
        enforceSymmetry: symmetryEnabled.value,
      },
    });
    evaluations.value = out.evaluations;
    bestProfileName.value = out.best?.profile.name ?? "";
    selectedProfileName.value = out.best?.profile.name ?? out.evaluations[0]?.profile.name ?? "";
    await runPreviewForGraph(
      out.bestResult?.graph ?? out.evaluations[0]?.result.graph ?? null,
      out.best?.profile.name ?? out.evaluations[0]?.profile.name ?? "",
    );
    lastRunAt.value = new Date().toLocaleString();
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : String(err);
  }
  busy.value = false;
}

onBeforeUnmount(() => {
  offProgress();
  engine.dispose();
});
</script>

<template>
  <main class="page">
    <section class="hero">
      <div class="hero-head">
        <div class="hero-title">
          <h1>Sqrt2 Origami Studio</h1>
          <p>{{ tr("1つのキャンバスで、配置→タイリング→展開図生成を行います。", "Single-canvas workflow: place points, run tiling, then generate crease patterns.") }}</p>
        </div>
        <div class="hero-actions">
          <label>
            {{ tr("言語", "Language") }}
            <select v-model="uiLang" class="mini-select">
              <option value="ja">日本語</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>
      </div>
    </section>

    <section class="panel left-panel">
      <nav class="left-tabs" role="tablist" :aria-label="tr('左ペインタブ', 'Left pane tabs')">
        <button
          class="left-tab"
          :class="{ active: leftPaneTab === 'run' }"
          type="button"
          role="tab"
          :aria-selected="leftPaneTab === 'run'"
          @click="leftPaneTab = 'run'"
        >
          {{ tr("実行", "Run") }}
        </button>
        <button
          class="left-tab"
          :class="{ active: leftPaneTab === 'global' }"
          type="button"
          role="tab"
          :aria-selected="leftPaneTab === 'global'"
          @click="leftPaneTab = 'global'"
        >
          {{ tr("全体設定", "Global") }}
        </button>
        <button
          class="left-tab"
          :class="{ active: leftPaneTab === 'points' }"
          type="button"
          role="tab"
          :aria-selected="leftPaneTab === 'points'"
          @click="leftPaneTab = 'points'"
        >
          {{ tr("点・辺", "Points & Edges") }}
        </button>
        <button
          class="left-tab"
          :class="{ active: leftPaneTab === 'generation' }"
          type="button"
          role="tab"
          :aria-selected="leftPaneTab === 'generation'"
          @click="leftPaneTab = 'generation'"
        >
          {{ tr("生成設定", "Generation") }}
        </button>
        <button
          class="left-tab"
          :class="{ active: leftPaneTab === 'info' }"
          type="button"
          role="tab"
          :aria-selected="leftPaneTab === 'info'"
          @click="leftPaneTab = 'info'"
        >
          Info
        </button>
      </nav>

      <div class="left-panel-body">
        <div v-show="leftPaneTab === 'run'" class="left-tab-page">
          <h2>{{ tr("実行", "Run") }}</h2>
          <div class="run-actions">
            <button class="btn ghost" :disabled="busy" @click="runTilingFromDesigner">{{ tr("タイリング", "Tiling") }}</button>
            <button class="btn" :disabled="busy" @click="runProfiles">{{ tr("展開図生成", "Run crease generation") }}</button>
            <button class="btn ghost" :disabled="busy || !selectedEvaluation" @click="runPreviewForSelectedProfile">
              {{ tr("折り上がり", "Run fold preview") }}
            </button>
          </div>
          <p v-if="lastRunAt" class="tip">{{ tr("最終実行", "Last run") }}: {{ lastRunAt }}</p>
          <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        </div>

        <div v-show="leftPaneTab === 'global'" class="left-tab-page">
          <h2>{{ tr("全体設定", "Global Settings") }}</h2>
          <div class="seed-edge-box">
            <h3>{{ tr("格子設定 (a, b, k)", "Lattice setting (a, b, k)") }}</h3>
            <div class="seed-segment-grid">
              <label>
                grid (a,b,k)
                <input v-model.number="aMaxInput" class="tiny-num" type="number" min="1" max="24" step="1" />
                <input v-model.number="bMaxInput" class="tiny-num" type="number" min="1" max="24" step="1" />
                <input v-model.number="kMaxInput" class="tiny-num" type="number" min="1" max="8" step="1" />
              </label>
            </div>
            <p class="tip seed-edge-tip">
              {{
                tr(
                  "a,b,k は (a+b√2)/2^k 格子の探索範囲です。a,b を上げると候補が増え、k を上げると分解能が上がります。",
                  "a,b,k define the search range of the (a+b*sqrt(2))/2^k lattice. Larger a,b increase candidates; larger k increases resolution.",
                )
              }}
            </p>
          </div>
          <div class="seed-edge-box">
            <h3>{{ tr("展開図生成の紙中心オフセット (dx, dy)", "Paper center offset for crease generation (dx, dy)") }}</h3>
            <div class="seed-segment-grid">
              <label>
                dx (a,b,k)
                <input v-model.number="originOffsetDraft.xA" class="tiny-num" type="number" step="1" />
                <input v-model.number="originOffsetDraft.xB" class="tiny-num" type="number" step="1" />
                <input v-model.number="originOffsetDraft.xK" class="tiny-num" type="number" min="0" step="1" />
              </label>
              <label>
                dy (a,b,k)
                <input v-model.number="originOffsetDraft.yA" class="tiny-num" type="number" step="1" />
                <input v-model.number="originOffsetDraft.yB" class="tiny-num" type="number" step="1" />
                <input v-model.number="originOffsetDraft.yK" class="tiny-num" type="number" min="0" step="1" />
              </label>
            </div>
            <p class="tip seed-edge-tip">
              approx: ({{ originOffsetApprox.x.toFixed(3) }}, {{ originOffsetApprox.y.toFixed(3) }})
              / {{ pointExactLabel(originOffsetExact) }}
            </p>
          </div>
        </div>

        <div v-show="leftPaneTab === 'points'" class="left-tab-page">
          <h2>{{ tr("点・辺設定", "Point & Edge Settings") }}</h2>
          <div v-if="selectedMeta && canvasEditMode === 'point'" class="selected-editor selected-editor-top">
            <h3>{{ tr("選択中の点", "Selected point") }}</h3>
            <p>{{ tr("グループ", "Group") }}: {{ selectedMeta.group }} / id: {{ selectedMeta.point.id }}</p>
            <label>
              x (a,b,k)
              <span class="coord-inputs">
                <input
                  :value="selectedPointExact ? selectedPointExact.x.a.toString() : '0'"
                  class="tiny-num"
                  type="number"
                  step="1"
                  @input="updateSelectedCoordExact('x', 'a', ($event.target as HTMLInputElement).value)"
                />
                <input
                  :value="selectedPointExact ? selectedPointExact.x.b.toString() : '0'"
                  class="tiny-num"
                  type="number"
                  step="1"
                  @input="updateSelectedCoordExact('x', 'b', ($event.target as HTMLInputElement).value)"
                />
                <input
                  :value="selectedPointExact ? selectedPointExact.x.k : 0"
                  class="tiny-num"
                  type="number"
                  min="0"
                  max="16"
                  step="1"
                  @input="updateSelectedCoordExact('x', 'k', ($event.target as HTMLInputElement).value)"
                />
              </span>
            </label>
            <label>
              y (a,b,k)
              <span class="coord-inputs">
                <input
                  :value="selectedPointExact ? selectedPointExact.y.a.toString() : '0'"
                  class="tiny-num"
                  type="number"
                  step="1"
                  @input="updateSelectedCoordExact('y', 'a', ($event.target as HTMLInputElement).value)"
                />
                <input
                  :value="selectedPointExact ? selectedPointExact.y.b.toString() : '0'"
                  class="tiny-num"
                  type="number"
                  step="1"
                  @input="updateSelectedCoordExact('y', 'b', ($event.target as HTMLInputElement).value)"
                />
                <input
                  :value="selectedPointExact ? selectedPointExact.y.k : 0"
                  class="tiny-num"
                  type="number"
                  min="0"
                  max="16"
                  step="1"
                  @input="updateSelectedCoordExact('y', 'k', ($event.target as HTMLInputElement).value)"
                />
              </span>
            </label>
            <p v-if="selectedPointExact" class="tip">
              x={{ qsqrt2Expr(selectedPointExact.x) }},
              y={{ qsqrt2Expr(selectedPointExact.y) }}
              / approx=({{ selectedMeta.point.x.toFixed(3) }}, {{ selectedMeta.point.y.toFixed(3) }})
            </p>
            <label>
              size
              <input
                :value="selectedMeta.point.size"
                type="number"
                min="0.2"
                max="3.0"
                step="0.1"
                @input="updateSelectedSize(Number(($event.target as HTMLInputElement).value))"
              />
            </label>
            <button class="btn danger" :disabled="busy" @click="deleteSelectedPoint">{{ tr("選択点を削除", "Delete selected point") }}</button>
          </div>
          <div class="settings-grid">
            <label class="check">
              <input v-model="symmetryEnabled" type="checkbox" />
              {{ tr("local y = x 対称", "local y = x symmetry") }}
            </label>
            <label class="check">
              <input v-model="showDesignerGrid" type="checkbox" />
              {{ tr("格子点を表示", "show grid points") }}
            </label>
            <label v-if="symmetryEnabled">
              {{ tr("追加モード", "placement") }}
              <select v-model="placementMode" class="mini-select">
                <option value="side">{{ tr("side（片側のみ）", "side (one side only)") }}</option>
                <option value="axis">{{ tr("axis（対称軸上）", "axis (on symmetry axis)") }}</option>
              </select>
            </label>
            <label>
              {{ tr("編集", "edit") }}
              <select v-model="canvasEditMode" class="mini-select">
                <option value="point">{{ tr("点", "points") }}</option>
                <option value="edge">{{ tr("初期辺", "seed edges") }}</option>
              </select>
            </label>
          </div>
          <p v-if="canvasEditMode === 'point'" class="tip">{{ tr("クリックで追加、ドラッグで移動。点は (a+b√2)/2^k 格子へ吸着します。", "Click to add and drag to move. Points snap to the (a+b*sqrt(2))/2^k lattice.") }}</p>
          <p v-else class="tip">{{ tr("初期辺編集: 角点/格子点を2回クリック、またはドラッグで始点→終点を指定してください。", "Seed-edge edit: click corner/grid points twice, or drag start to end.") }}</p>
          <p v-if="canvasEditMode === 'edge' && edgeDraftStartPick">
            {{ tr("始点", "start") }}:
            <span v-if="edgeDraftStartPick.cornerIdx !== null">#{{ edgeDraftStartPick.cornerIdx }}</span>
            <span v-else>({{ edgeDraftStartPick.x.toFixed(3) }}, {{ edgeDraftStartPick.y.toFixed(3) }})</span>
          </p>
          <p>{{ tr("現在のカド数（境界込み）", "Current corner count (with boundary)") }}: {{ activeCorners.length }}</p>
          <p v-if="symmetryEnabled">{{ tr("Axis", "Axis") }}: {{ axisPoints.length }} / {{ tr("Side（片側）", "Side (one side)") }}: {{ sidePoints.length }}</p>
          <p v-else>{{ tr("Free", "Free") }}: {{ freePoints.length }}</p>
          <div class="seed-edge-box">
            <h3>{{ tr("初期辺・格子セグメント", "Seed edges & grid segments") }}</h3>
            <div class="seed-edge-row">
              <label class="check">
                <input
                  v-model="seedEdgeAutoMirror"
                  type="checkbox"
                  :disabled="busy || !symmetryEnabled"
                />
                {{ tr("辺: local y=x で自動ミラー", "edges: auto mirror by local y=x") }}
              </label>
              <label class="check">
                <input
                  v-model="seedSegmentAutoMirror"
                  type="checkbox"
                  :disabled="busy || !symmetryEnabled"
                />
                {{ tr("セグメント: local y=x で自動ミラー", "segments: auto mirror by local y=x") }}
              </label>
              <button class="btn ghost" :disabled="busy || seedEdges.length <= 0" @click="clearSeedEdges">
                {{ tr("辺をクリア", "Clear edges") }}
              </button>
              <button class="btn ghost" :disabled="busy || seedSegments.length <= 0" @click="clearSeedSegments">
                {{ tr("セグメントをクリア", "Clear segments") }}
              </button>
            </div>
            <p class="tip seed-edge-tip">
              {{ tr("キャンバスの編集モードを「初期辺」にすると、クリック/ドラッグで辺・セグメントを直接追加できます。", "Switch canvas edit mode to 'seed edges' to add edges/segments directly by click/drag.") }}
              <br />
              {{ tr("辺 raw/run", "Edges raw/run") }}: {{ seedEdges.length }} / {{ seedEdgesForRun.length }}
              <span v-if="seedEdgeAutoAddedCount > 0"> ( +{{ seedEdgeAutoAddedCount }} {{ tr("自動ミラー", "auto mirror") }} )</span>
              ,
              {{ tr("セグメント raw/run", "Segments raw/run") }}: {{ seedSegments.length }} / {{ seedSegmentsForRun.length }}
              <span v-if="seedSegmentAutoAddedCount > 0"> ( +{{ seedSegmentAutoAddedCount }} {{ tr("自動ミラー", "auto mirror") }} )</span>
            </p>
          </div>
          <div class="row-btn">
            <button class="btn ghost" :disabled="busy" @click="loadSampleLayoutBasic">{{ tr("サンプル配置", "Load sample layout") }}</button>
            <button class="btn ghost" :disabled="busy" @click="clearDesignerInteriorPoints">{{ tr("内部点をクリア", "Clear interior points") }}</button>
            <button class="btn ghost" :disabled="busy" @click="resetDesignerDefaults">{{ tr("既定値に戻す", "Reset defaults") }}</button>
          </div>
        </div>

        <div v-show="leftPaneTab === 'generation'" class="left-tab-page">
          <h2>{{ tr("生成設定", "Generation Settings") }}</h2>
          <div class="seed-edge-box modal-section">
            <h3>{{ tr("タイリング最適化", "Tiling optimization") }}</h3>
            <p class="tip seed-edge-tip">
              {{
                tr(
                  "タイリング格子はキャンバスと同じ a,b,k を使用します。",
                  "Tiling uses the same a,b,k lattice as the canvas.",
                )
              }}
            </p>
            <div class="modal-field-grid">
              <div class="modal-field">
                <label>
                  seed
                  <input v-model.number="tilingSeed" type="number" step="1" />
                </label>
                <p class="field-help">{{ tr("探索の乱数シード。変えると別解が出やすくなります。", "Random seed for search. Changing it helps find alternative solutions.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  alpha steps
                  <input v-model.number="tilingAlphaSteps" type="number" min="1" max="64" />
                </label>
                <p class="field-help">{{ tr("半径探索の段数。増やすと探索が細かくなります。", "Number of radius search steps. Larger values refine the search.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  pack restarts
                  <input v-model.number="tilingPackRestarts" type="number" min="1" max="200" />
                </label>
                <p class="field-help">{{ tr("初期配置の試行回数。増やすと成功率が上がる場合があります。", "Number of packing retries. Larger values can improve success rate.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  pack iters
                  <input v-model.number="tilingPackIters" type="number" min="1" max="5000" />
                </label>
                <p class="field-help">{{ tr("1回あたりの調整反復回数。増やすと収束しやすくなります。", "Adjustment iterations per retry. Larger values can improve convergence.") }}</p>
              </div>
            </div>
          </div>

          <div class="seed-edge-box modal-section">
            <h3>{{ tr("展開図探索予算", "Crease search budget") }}</h3>
            <div class="modal-field-grid">
              <div class="modal-field">
                <label>
                  {{ tr("max depth", "max depth") }}
                  <input v-model.number="searchMaxDepthInput" class="tiny-num" type="number" min="1" max="64" step="1" />
                </label>
                <p class="field-help">{{ tr("探索の深さ上限。大きいほど広く探します。", "Maximum search depth. Larger values explore deeper.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  {{ tr("branch/node", "branch/node") }}
                  <input v-model.number="searchBranchPerNodeInput" class="tiny-num" type="number" min="1" max="64" step="1" />
                </label>
                <p class="field-help">{{ tr("各ノードで分岐させる候補数です。", "Number of branch candidates per node.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  {{ tr("max nodes", "max nodes") }}
                  <input v-model.number="searchMaxNodesInput" class="tiny-num" type="number" min="1" max="200000" step="1" />
                </label>
                <p class="field-help">{{ tr("探索全体で展開するノード数の上限です。", "Upper limit on expanded nodes for the whole search.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  allowViolations
                  <input v-model.number="searchAllowViolationsInput" class="tiny-num" type="number" min="0" max="64" step="1" />
                </label>
                <p class="field-help">{{ tr("カド条件違反を何件まで許容して探索を継続するかです。", "How many corner-condition violations can be tolerated during search.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  dirTopK
                  <input v-model.number="searchDirTopKInput" class="tiny-num" type="number" min="1" max="16" step="1" />
                </label>
                <p class="field-help">{{ tr("方向候補の上位何件を使うかを指定します。", "How many top direction candidates are used.") }}</p>
              </div>
              <div class="modal-field">
                <label>
                  priorityTopN
                  <input v-model.number="searchPriorityTopNInput" class="tiny-num" type="number" min="1" max="32" step="1" />
                </label>
                <p class="field-help">{{ tr("優先頂点候補として保持する件数です。", "How many priority vertex candidates are retained.") }}</p>
              </div>
            </div>
          </div>
        </div>

        <div v-show="leftPaneTab === 'info'" class="left-tab-page">
          <h2>Info</h2>
          <div class="seed-edge-box">
            <h3>{{ tr("アプリ概要", "About") }}</h3>
            <p class="tip">{{ tr(APP_INFO.summaryJa, APP_INFO.summaryEn) }}</p>
            <p class="tip">
              <strong>{{ tr("フロー", "Flow") }}:</strong>
              {{ tr(APP_INFO.flowJa, APP_INFO.flowEn) }}
            </p>
          </div>

          <div class="seed-edge-box">
            <h3>{{ tr("作者 / SNS", "Author / Social") }}</h3>
            <p><strong>{{ tr("作者", "Author") }}:</strong> {{ APP_INFO.authorName }}</p>
            <div class="info-links">
              <a
                v-for="link in APP_INFO.socialLinks"
                :key="`info_social_${link.label}`"
                :href="link.url"
                target="_blank"
                rel="noreferrer noopener"
                class="info-link"
              >
                {{ link.label }}
              </a>
            </div>
          </div>

          <div class="seed-edge-box">
            <h3>{{ tr("リポジトリ / ライセンス", "Repository / License") }}</h3>
            <div class="info-links">
              <a
                :href="APP_INFO.repositoryUrl"
                target="_blank"
                rel="noreferrer noopener"
                class="info-link"
              >
                GitHub Repository
              </a>
            </div>
            <p class="tip">
              {{ tr("ライセンス", "License") }}: {{ APP_INFO.licenseName }}
              ({{ tr("リポジトリの LICENSE を参照", "see LICENSE in repository") }})
            </p>
          </div>
        </div>
      </div>
    </section>

    <section class="panel designer">
      <h2>{{ tr("紙キャンバス", "Paper Canvas") }}</h2>
      <svg
        ref="designerSvg"
        :viewBox="`0 0 ${CANVAS_SIZE} ${CANVAS_SIZE}`"
        class="designer-canvas"
        @click="onCanvasClick"
        @pointerdown="onCanvasPointerDown"
        @pointermove="onCanvasPointerMove"
        @pointerup="onCanvasPointerUp"
        @pointerleave="onCanvasPointerUp"
      >
        <rect x="0" y="0" :width="CANVAS_SIZE" :height="CANVAS_SIZE" class="box" />
        <g v-if="canvasEditMode === 'edge'">
          <line
            v-for="e in seedEdgeCanvasLines"
            :key="`seed_edge_canvas_${e.key}`"
            :x1="toCanvasX(e.x1)"
            :y1="toCanvasY(e.y1)"
            :x2="toCanvasX(e.x2)"
            :y2="toCanvasY(e.y2)"
            class="seed-edge-line"
          />
          <line
            v-for="s in seedSegmentCanvasLines"
            :key="`seed_segment_canvas_${s.key}`"
            :x1="toCanvasX(s.x1)"
            :y1="toCanvasY(s.y1)"
            :x2="toCanvasX(s.x2)"
            :y2="toCanvasY(s.y2)"
            class="seed-segment-line"
          />
          <line
            v-if="edgeDraftLine"
            :x1="toCanvasX(edgeDraftLine.x1)"
            :y1="toCanvasY(edgeDraftLine.y1)"
            :x2="toCanvasX(edgeDraftLine.x2)"
            :y2="toCanvasY(edgeDraftLine.y2)"
            class="seed-edge-preview"
          />
        </g>
        <line
          v-if="symmetryAxisLine"
          :x1="toCanvasX(symmetryAxisLine.x1)"
          :y1="toCanvasY(symmetryAxisLine.y1)"
          :x2="toCanvasX(symmetryAxisLine.x2)"
          :y2="toCanvasY(symmetryAxisLine.y2)"
          class="axis-line"
        />
        <g v-if="showDesignerGrid">
          <circle
            v-for="g in designerGridDots"
            :key="`grid_${g.key}`"
            :cx="toCanvasX(g.x)"
            :cy="toCanvasY(g.y)"
            r="0.9"
            class="grid-dot"
          />
        </g>
        <g v-if="symmetryEnabled">
          <circle
            v-for="p in mirroredSidePoints"
            :key="`mirror_${p.id}`"
            :cx="toCanvasX(p.x)"
            :cy="toCanvasY(p.y)"
            :r="pointRadius(p)"
            class="pt mirror"
          />
        </g>
        <g v-if="symmetryEnabled">
          <circle
            v-for="p in axisPoints"
            :key="`axis_${p.id}`"
            :cx="toCanvasX(p.x)"
            :cy="toCanvasY(p.y)"
            :r="pointRadius(p)"
            class="pt axis"
            :data-corner-id="p.id"
            @pointerdown="onPointPointerDown('axis', p.id, $event)"
          />
          <circle
            v-for="p in sidePoints"
            :key="`side_${p.id}`"
            :cx="toCanvasX(p.x)"
            :cy="toCanvasY(p.y)"
            :r="pointRadius(p)"
            class="pt side"
            :data-corner-id="p.id"
            @pointerdown="onPointPointerDown('side', p.id, $event)"
          />
        </g>
        <g v-else>
          <circle
            v-for="p in freePoints"
            :key="`free_${p.id}`"
            :cx="toCanvasX(p.x)"
            :cy="toCanvasY(p.y)"
            :r="pointRadius(p)"
            class="pt free"
            :data-corner-id="p.id"
            @pointerdown="onPointPointerDown('free', p.id, $event)"
          />
        </g>
        <g v-if="canvasEditMode === 'edge'">
          <circle
            v-for="c in activeCornerCanvasPoints"
            :key="`active_corner_dot_${c.idx}`"
            :cx="toCanvasX(c.x)"
            :cy="toCanvasY(c.y)"
            r="3.6"
            :class="edgeDraftStartPick && edgeDraftStartPick.cornerIdx === c.idx ? 'active-corner-dot start' : 'active-corner-dot'"
          />
          <circle
            v-for="c in activeCornerCanvasPoints"
            :key="`active_corner_hit_${c.idx}`"
            :cx="toCanvasX(c.x)"
            :cy="toCanvasY(c.y)"
            r="8"
            class="active-corner-hit"
            :data-active-corner-idx="c.idx"
            @pointerdown="onActiveCornerPointerDown(c.idx, $event)"
          />
        </g>
      </svg>
    </section>

    <section class="panel cp-view">
      <h2>Crease Pattern View</h2>
      <div v-if="evaluations.length > 0" class="cp-view-top">
        <label>
          profile
          <select
            :value="selectedEvaluation?.profile.name ?? ''"
            class="select"
            @change="selectProfileForPreview(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="ev in evaluations" :key="`cp_view_${ev.profile.name}`" :value="ev.profile.name">
              {{ ev.profile.name }}
            </option>
          </select>
        </label>
        <span v-if="selectedEvaluation">showing: {{ selectedEvaluation.profile.name }}</span>
        <label>
          {{ tr("書出形式", "Export mode") }}
          <select v-model="cpGraphExportPolicy" class="mini-select" :disabled="busy || !selectedGraph">
            <option value="centered_world">{{ tr("centered/world", "centered/world") }}</option>
            <option value="legacy_unit">{{ tr("legacy [0,1]", "legacy [0,1]") }}</option>
          </select>
        </label>
        <button class="btn ghost" :disabled="busy || !selectedGraph" @click="exportSelectedCpGraph">
          {{ tr("cp_graph_v1 JSON 書出", "Export cp_graph_v1 JSON") }}
        </button>
        <button class="btn ghost" :disabled="busy || !selectedGraph" @click="exportSelectedOripaCp">
          {{ tr("ORIPA .cp 書出", "Export ORIPA .cp") }}
        </button>
      </div>
      <div v-if="cpViewData" class="cp-view-wrap">
        <svg :viewBox="`0 0 ${CP_VIEW_SIZE} ${CP_VIEW_SIZE}`" class="cp-view-canvas">
          <rect x="0" y="0" :width="CP_VIEW_SIZE" :height="CP_VIEW_SIZE" class="cp-box" />
          <line
            v-for="(seg, idx) in cpViewData.edgeLines"
            :key="`cp_edge_${idx}`"
            :x1="seg.x1"
            :y1="seg.y1"
            :x2="seg.x2"
            :y2="seg.y2"
            :class="seg.boundary ? 'cp-edge boundary' : 'cp-edge internal'"
          />
          <circle
            v-for="p in cpViewData.pointMarks"
            :key="`cp_point_${p.id}`"
            :cx="p.x"
            :cy="p.y"
            :class="p.corner ? 'cp-point corner' : p.boundary ? 'cp-point boundary' : 'cp-point internal'"
            :r="p.corner ? 3.2 : 2.2"
          />
        </svg>
        <div class="cp-view-meta">
          <p>vertex: {{ cpViewData.stats.vertexCount }}</p>
          <p>edge: {{ cpViewData.stats.edgeCount }}</p>
          <p>boundary edge: {{ cpViewData.stats.boundaryEdgeCount }}</p>
          <p>corner: {{ cpViewData.stats.cornerCount }}</p>
        </div>
      </div>
      <p v-if="selectedGraph" class="tip">
        {{
          tr(
            "ORIPA .cp 書出では、境界線=1(cut)、内部線=2(ridge)として保存します（現状、山谷の明示割当は未実装）。",
            "ORIPA .cp export saves boundary edges as type 1 (cut) and internal edges as type 2 (ridge). Explicit M/V assignment is not implemented yet.",
          )
        }}
      </p>
      <p v-else class="empty">No generated crease pattern yet.</p>
    </section>

    <section class="panel fold-view">
      <h2>Folded Preview</h2>
      <div class="fold-top">
        <button class="btn" :disabled="busy || !selectedEvaluation" @click="runPreviewForSelectedProfile">
          Run Fold Preview (Selected Profile)
        </button>
        <label>
          alpha
          <input v-model.number="previewAlpha" type="number" step="0.1" />
        </label>
        <label>
          line width
          <input v-model.number="previewLineWidth" type="number" min="0.2" max="8" step="0.1" />
        </label>
        <label class="check">
          <input v-model="previewShowFaceId" type="checkbox" />
          face id
        </label>
        <span v-if="previewProfileName">preview profile: {{ previewProfileName }}</span>
      </div>
      <div v-if="foldViewData" class="fold-view-wrap">
        <svg :viewBox="`0 0 ${FOLD_VIEW_SIZE} ${FOLD_VIEW_SIZE}`" class="fold-view-canvas">
          <rect x="0" y="0" :width="FOLD_VIEW_SIZE" :height="FOLD_VIEW_SIZE" class="fold-box" />
          <polygon
            v-for="f in foldViewData.faces"
            :key="`fold_face_${f.faceId}`"
            :points="f.pointsAttr"
            :fill="f.fill"
            :fill-opacity="f.fillOpacity"
            class="fold-face"
            :style="{ strokeWidth: `${previewLineWidth}` }"
          />
          <text
            v-if="previewShowFaceId"
            v-for="f in foldViewData.faces"
            :key="`fold_face_label_${f.faceId}`"
            :x="f.cx"
            :y="f.cy"
            class="fold-face-label"
          >
            {{ f.faceId }}
          </text>
        </svg>
        <div class="cp-view-meta">
          <p>segment: {{ foldViewData.stats.segmentCount }}</p>
          <p>face: {{ foldViewData.stats.faceCount }}</p>
          <p>dual edge: {{ foldViewData.stats.dualEdgeCount }}</p>
          <p>inconsistency: {{ foldViewData.stats.transformInconsistencies }}</p>
        </div>
      </div>
      <p v-else class="empty">No folded preview yet.</p>
    </section>

    <div v-if="busy" class="progress-overlay" aria-busy="true" aria-live="polite">
      <div class="progress-overlay-card">
        <svg viewBox="0 0 128 128" class="progress-ring-canvas">
          <circle class="progress-ring-track" cx="64" cy="64" :r="progressRingRadius" />
          <circle
            class="progress-ring-fill"
            cx="64"
            cy="64"
            :r="progressRingRadius"
            :stroke-dasharray="progressRingCircumference"
            :stroke-dashoffset="(1 - progressRatioClamped) * progressRingCircumference"
          />
        </svg>
        <p>{{ Math.round(progressRatioClamped * 100) }}%</p>
      </div>
    </div>
  </main>
</template>

