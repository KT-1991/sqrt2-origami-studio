<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { WorkerOrigamiEngine } from "../src/engine/client";
import { cpGraphV1ToMemGraph } from "../src/engine/cp_graph_adapters";
import {
  DEFAULT_REAL_DATA_EVAL_PROFILES,
  type CreasegenProfileEvaluation,
} from "../src/engine/creasegen_profiles";
import { ONE, ZERO, fromDyadic, fromInt, q2Cmp, qsqrt2, qsqrt2Approx } from "../src/engine/qsqrt2";
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

interface PresetCpGraph {
  label: string;
  path: string;
}

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

const PRESET_CP_GRAPHS: PresetCpGraph[] = [
  { label: "cp_graph_test2 (sample)", path: "/samples/cp_graph_test2.json" },
  { label: "cp_graph_test", path: "/samples/cp_graph_test.json" },
];

const CANVAS_SIZE = 360;
const CP_VIEW_SIZE = 460;
const FOLD_VIEW_SIZE = 460;

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function clampInt(v: number, min: number, max: number): number {
  if (!Number.isFinite(v)) {
    return min;
  }
  return Math.max(min, Math.min(max, Math.round(v)));
}

function parsePositiveIntCsv(text: string): number[] {
  const out: number[] = [];
  for (const part of text.split(",")) {
    const t = part.trim();
    if (t.length === 0) {
      continue;
    }
    const v = Number(t);
    if (!Number.isInteger(v) || v <= 0) {
      throw new Error(`invalid positive integer list: ${text}`);
    }
    out.push(v);
  }
  if (out.length <= 0) {
    throw new Error("candidate list must not be empty");
  }
  return [...new Set(out)];
}

function sampleCorners(): PointE[] {
  const z = fromInt(0);
  const o = fromInt(1);
  const h = fromDyadic(1, 1);
  return [
    { x: z, y: z },
    { x: z, y: o },
    { x: o, y: z },
    { x: o, y: o },
    { x: h, y: h },
  ];
}

function cornersFromCpGraph(payload: CpGraphV1Json): PointE[] {
  const g = cpGraphV1ToMemGraph(payload);
  const byId = new Map<number, PointE>();
  for (const v of g.vertices) {
    byId.set(v.id, v.point);
  }
  const out: PointE[] = [];
  for (const id of [...g.corners].sort((a, b) => a - b)) {
    const p = byId.get(id);
    if (!p) {
      throw new Error(`corner id ${id} is missing in vertices`);
    }
    out.push(p);
  }
  if (out.length < 3) {
    throw new Error("corner count must be >= 3");
  }
  return out;
}

function num(v: number): string {
  return Number.isFinite(v) ? String(v) : "-";
}

const uiLang = ref<"ja" | "en">("ja");

function tr(ja: string, en: string): string {
  return uiLang.value === "ja" ? ja : en;
}

function pointExactKey(p: PointE): string {
  return `${p.x.a.toString()}_${p.x.b.toString()}_${p.x.k}|${p.y.a.toString()}_${p.y.b.toString()}_${p.y.k}`;
}

function mirroredPointExactKey(p: PointE): string {
  return `${p.y.a.toString()}_${p.y.b.toString()}_${p.y.k}|${p.x.a.toString()}_${p.x.b.toString()}_${p.x.k}`;
}

function qsqrt2Short(z: PointE["x"]): string {
  return `${z.a.toString()},${z.b.toString()},${z.k}`;
}

function pointExactLabel(p: PointE): string {
  return `x(${qsqrt2Short(p.x)}) y(${qsqrt2Short(p.y)})`;
}

function pointApproxLabel(p: PointE): string {
  return `(${qsqrt2Approx(p.x).toFixed(3)}, ${qsqrt2Approx(p.y).toFixed(3)})`;
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

const symmetryEnabled = ref(true);
const placementMode = ref<"axis" | "side">("side");
const aMaxInput = ref(2);
const bMaxInput = ref(2);
const kMaxInput = ref(2);

const tilingSeed = ref(0);
const tilingDenCandidates = ref("1,2");
const tilingCoeffCandidates = ref("1,2");
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

const selectedPresetPath = ref<string>(PRESET_CP_GRAPHS[0].path);
const sourceMode = ref<"designer" | "external">("designer");
const externalCorners = ref<PointE[]>(sampleCorners());
const externalSourceLabel = ref<string>("sample corners");
const seedEdges = ref<CreaseSeedEdgeInput[]>([]);
const seedEdgeI = ref(0);
const seedEdgeJ = ref(1);
const seedEdgeAutoMirror = ref(true);
const seedSegments = ref<CreaseSeedSegmentInput[]>([]);
const seedSegmentAutoMirror = ref(true);
const seedSegmentDraft = ref({
  fromXa: 0,
  fromXb: 0,
  fromXk: 0,
  fromYa: 0,
  fromYb: 0,
  fromYk: 0,
  toXa: 1,
  toXb: 0,
  toXk: 0,
  toYa: 1,
  toYb: 0,
  toYk: 0,
});

const nextPointId = ref(1);
const axisPoints = ref<DesignerPoint[]>([{ id: nextPointId.value++, x: 0.5, y: 0.5, size: 1 }]);
const sidePoints = ref<DesignerPoint[]>([]);
const freePoints = ref<DesignerPoint[]>([{ id: nextPointId.value++, x: 0.5, y: 0.5, size: 1 }]);
const showDesignerGrid = ref(true);
const canvasEditMode = ref<"point" | "edge">("point");
const edgeDraftStartPick = ref<EdgePick | null>(null);
const edgeDraftPointer = ref<{ x: number; y: number } | null>(null);
const edgeDragStartPick = ref<EdgePick | null>(null);
const edgeDragMoved = ref(false);

const designerSvg = ref<SVGSVGElement | null>(null);
const dragState = ref<{ group: DesignerGroup; id: number } | null>(null);
const selectedPoint = ref<{ group: DesignerGroup; id: number } | null>(null);

const latticeValues = computed<LatticeValue[]>(() => {
  const aMax = clampInt(aMaxInput.value, 1, 24);
  const bMax = clampInt(bMaxInput.value, 1, 24);
  const kMax = clampInt(kMaxInput.value, 0, 8);
  const byKey = new Map<string, LatticeValue>();
  for (let k = 0; k <= kMax; k += 1) {
    for (let a = -aMax; a <= aMax; a += 1) {
      for (let b = -bMax; b <= bMax; b += 1) {
        const z = qsqrt2(a, b, k);
        if (q2Cmp(z, ZERO) < 0 || q2Cmp(z, ONE) > 0) {
          continue;
        }
        const key = `${z.a.toString()}_${z.b.toString()}_${z.k}`;
        if (byKey.has(key)) {
          continue;
        }
        byKey.set(key, {
          key,
          exact: z,
          approx: clamp01(qsqrt2Approx(z)),
        });
      }
    }
  }
  const out = [...byKey.values()].sort((lhs, rhs) => lhs.approx - rhs.approx);
  if (out.length <= 0) {
    return [
      { key: "0_0_0", exact: fromInt(0), approx: 0 },
      { key: "1_0_0", exact: fromInt(1), approx: 1 },
    ];
  }
  return out;
});

const latticeStep = computed(() => {
  const values = latticeValues.value;
  if (values.length <= 1) {
    return 0.001;
  }
  let minStep = Number.POSITIVE_INFINITY;
  for (let i = 1; i < values.length; i += 1) {
    const d = Math.abs(values[i].approx - values[i - 1].approx);
    if (d > 1e-12 && d < minStep) {
      minStep = d;
    }
  }
  if (!Number.isFinite(minStep)) {
    return 0.001;
  }
  return Number(minStep.toPrecision(8));
});

function nearestLatticeIndex(vIn: number): number {
  const values = latticeValues.value;
  if (values.length <= 1) {
    return 0;
  }
  const v = clamp01(vIn);
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

function latticeValueAt(index: number): LatticeValue {
  const values = latticeValues.value;
  if (values.length <= 0) {
    return { key: "0_0_0", exact: fromInt(0), approx: 0 };
  }
  const i = Math.max(0, Math.min(values.length - 1, index));
  return values[i];
}

function pointRadius(p: DesignerPoint): number {
  return Math.max(4, Math.min(12, 4 + p.size * 2));
}

function toCanvasX(u: number): number {
  return clamp01(u) * CANVAS_SIZE;
}

function toCanvasY(v: number): number {
  return (1 - clamp01(v)) * CANVAS_SIZE;
}

function normalizePoint(group: DesignerGroup, xIn: number, yIn: number): { x: number; y: number } {
  let ix = nearestLatticeIndex(xIn);
  let iy = nearestLatticeIndex(yIn);

  if (!symmetryEnabled.value || group === "free") {
    return {
      x: latticeValueAt(ix).approx,
      y: latticeValueAt(iy).approx,
    };
  }

  if (group === "axis") {
    const im = nearestLatticeIndex((xIn + yIn) * 0.5);
    const m = latticeValueAt(im).approx;
    return { x: m, y: m };
  }

  if (latticeValueAt(ix).approx > latticeValueAt(iy).approx) {
    const t = ix;
    ix = iy;
    iy = t;
  }
  if (ix === iy) {
    const values = latticeValues.value;
    if (iy + 1 < values.length) {
      iy += 1;
    } else if (ix > 0) {
      ix -= 1;
    }
  }
  return {
    x: latticeValueAt(ix).approx,
    y: latticeValueAt(iy).approx,
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
  sourceMode.value = "designer";
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
  const rect = svg.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    return null;
  }
  const x = (ev.clientX - rect.left) / rect.width;
  const y = 1 - (ev.clientY - rect.top) / rect.height;
  return { x: clamp01(x), y: clamp01(y) };
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
  sourceMode.value = "designer";
}

function buildPickFromNorm(x: number, y: number): EdgePick {
  const vx = latticeValueAt(nearestLatticeIndex(x));
  const vy = latticeValueAt(nearestLatticeIndex(y));
  const point: PointE = { x: vx.exact, y: vy.exact };
  const key = pointExactKey(point);
  return {
    key,
    point,
    x: vx.approx,
    y: vy.approx,
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
    x: clamp01(qsqrt2Approx(point.x)),
    y: clamp01(qsqrt2Approx(point.y)),
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
  sourceMode.value = "designer";
}

function clearDesignerInteriorPoints(): void {
  axisPoints.value = [];
  sidePoints.value = [];
  freePoints.value = [];
  selectedPoint.value = null;
  sourceMode.value = "designer";
}

function resetDesignerDefaults(): void {
  axisPoints.value = [{ id: nextPointId.value++, x: 0.5, y: 0.5, size: 1 }];
  sidePoints.value = [];
  freePoints.value = [{ id: nextPointId.value++, x: 0.5, y: 0.5, size: 1 }];
  selectedPoint.value = null;
  sourceMode.value = "designer";
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

function updateSelectedCoord(axis: "x" | "y", raw: string): void {
  if (!selectedMeta.value) {
    return;
  }
  const v = Number(raw);
  if (!Number.isFinite(v)) {
    return;
  }
  const x = axis === "x" ? v : selectedMeta.value.point.x;
  const y = axis === "y" ? v : selectedMeta.value.point.y;
  updatePoint(selectedMeta.value.group, selectedMeta.value.point.id, x, y);
}

const designerGridDots = computed(() => {
  if (!showDesignerGrid.value) {
    return [] as Array<{ x: number; y: number; key: string }>;
  }
  const values = latticeValues.value;
  if (values.length <= 0) {
    return [] as Array<{ x: number; y: number; key: string }>;
  }
  const n = values.length;
  const total = n * n;
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
    out.push({ x: values[ix].approx, y: values[iy].approx, key });
  }
  for (let ix = 0; ix < n; ix += stride) {
    for (let iy = 0; iy < n; iy += stride) {
      add(ix, iy);
    }
  }
  for (let i = 0; i < n; i += stride) {
    add(i, n - 1);
    add(n - 1, i);
  }
  add(0, 0);
  add(0, n - 1);
  add(n - 1, 0);
  add(n - 1, n - 1);
  return out;
});

const designerCorners = computed<PointE[]>(() => {
  const coords = new Map<string, PointE>();

  function addXY(x: number, y: number): void {
    const px = latticeValueAt(nearestLatticeIndex(x)).exact;
    const py = latticeValueAt(nearestLatticeIndex(y)).exact;
    const p: PointE = { x: px, y: py };
    coords.set(pointExactKey(p), p);
  }

  addXY(0, 0);
  addXY(0, 1);
  addXY(1, 0);
  addXY(1, 1);

  if (symmetryEnabled.value) {
    for (const p of axisPoints.value) {
      addXY(p.x, p.y);
    }
    for (const p of sidePoints.value) {
      addXY(p.x, p.y);
      addXY(p.y, p.x);
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

const activeCorners = computed<PointE[]>(() =>
  sourceMode.value === "designer" ? designerCorners.value : externalCorners.value,
);

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
    x: clamp01(qsqrt2Approx(p.x)),
    y: clamp01(qsqrt2Approx(p.y)),
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
    x1: clamp01(qsqrt2Approx(seg.from.x)),
    y1: clamp01(qsqrt2Approx(seg.from.y)),
    x2: clamp01(qsqrt2Approx(seg.to.x)),
    y2: clamp01(qsqrt2Approx(seg.to.y)),
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

const sourceLabel = computed(() =>
  sourceMode.value === "designer"
    ? tr("カドキャンバス", "corner canvas")
    : externalSourceLabel.value,
);

const activeCornerRows = computed(() =>
  activeCorners.value.map((p, idx) => ({
    idx,
    approx: pointApproxLabel(p),
    exact: pointExactLabel(p),
  })),
);

const cornerOptions = computed(() =>
  activeCorners.value.map((p, idx) => ({
    idx,
    label: `${idx}: (${qsqrt2Approx(p.x).toFixed(3)}, ${qsqrt2Approx(p.y).toFixed(3)})`,
  })),
);

function cornerLabel(idx: number): string {
  if (idx < 0 || idx >= activeCorners.value.length) {
    return `${idx}: invalid`;
  }
  return cornerOptions.value[idx].label;
}

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
      x1: clamp01(v0.pointApprox.x) * CP_VIEW_SIZE,
      y1: (1 - clamp01(v0.pointApprox.y)) * CP_VIEW_SIZE,
      x2: clamp01(v1.pointApprox.x) * CP_VIEW_SIZE,
      y2: (1 - clamp01(v1.pointApprox.y)) * CP_VIEW_SIZE,
      boundary: e.isBoundary,
    });
  }

  const cornerIds = new Set<number>(graph.corners);
  const pointMarks = graph.vertices.map((v) => ({
    id: v.id,
    x: clamp01(v.pointApprox.x) * CP_VIEW_SIZE,
    y: (1 - clamp01(v.pointApprox.y)) * CP_VIEW_SIZE,
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
    from: { x: seg.from.y, y: seg.from.x },
    to: { x: seg.to.y, y: seg.to.x },
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

function seedSegmentLabel(seg: CreaseSeedSegmentInput): string {
  const fa = qsqrt2Approx(seg.from.x).toFixed(3);
  const fb = qsqrt2Approx(seg.from.y).toFixed(3);
  const ta = qsqrt2Approx(seg.to.x).toFixed(3);
  const tb = qsqrt2Approx(seg.to.y).toFixed(3);
  return `(${fa}, ${fb}) -> (${ta}, ${tb})`;
}

function addSeedSegmentFromDraft(): void {
  const d = seedSegmentDraft.value;
  const from: PointE = {
    x: qsqrt2(Math.trunc(d.fromXa), Math.trunc(d.fromXb), clampInt(d.fromXk, 0, 16)),
    y: qsqrt2(Math.trunc(d.fromYa), Math.trunc(d.fromYb), clampInt(d.fromYk, 0, 16)),
  };
  const to: PointE = {
    x: qsqrt2(Math.trunc(d.toXa), Math.trunc(d.toXb), clampInt(d.toXk, 0, 16)),
    y: qsqrt2(Math.trunc(d.toYa), Math.trunc(d.toYb), clampInt(d.toYk, 0, 16)),
  };
  const n = normalizedSeedSegment({ from, to });
  if (!n) {
    errorMessage.value = "invalid seed segment: from and to must be different points";
    return;
  }
  const key = seedSegmentKey(n);
  if (seedSegments.value.some((s) => seedSegmentKey(normalizedSeedSegment(s) ?? s) === key)) {
    return;
  }
  errorMessage.value = "";
  seedSegments.value = [...seedSegments.value, n];
}

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

function removeSeedSegmentAt(index: number): void {
  if (index < 0 || index >= seedSegments.value.length) {
    return;
  }
  const out = [...seedSegments.value];
  out.splice(index, 1);
  seedSegments.value = out;
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

  if (count <= 0) {
    seedEdgeI.value = 0;
    seedEdgeJ.value = 0;
    return;
  }
  seedEdgeI.value = clampInt(seedEdgeI.value, 0, count - 1);
  seedEdgeJ.value = clampInt(seedEdgeJ.value, 0, count - 1);
  if (count > 1 && seedEdgeI.value === seedEdgeJ.value) {
    seedEdgeJ.value = seedEdgeI.value === 0 ? 1 : 0;
  }
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

function addSeedEdge(): void {
  addSeedEdgeByCornerIndices(seedEdgeI.value, seedEdgeJ.value);
}

function removeSeedEdgeAt(index: number): void {
  if (index < 0 || index >= seedEdges.value.length) {
    return;
  }
  const out = [...seedEdges.value];
  out.splice(index, 1);
  seedEdges.value = out;
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
watch(canvasEditMode, () => {
  edgeDraftStartPick.value = null;
  edgeDraftPointer.value = null;
  edgeDragStartPick.value = null;
  edgeDragMoved.value = false;
});

function buildTilingInputFromDesigner(): TilingRunInput {
  if (!symmetryEnabled.value) {
    throw new Error("tiling stage currently expects y=x symmetry mode to be ON");
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
    initialCenters[r] = { x: p.y, y: p.x };
  }

  if (specs.length <= 0) {
    throw new Error("no interior kado points to optimize; add axis or side points first");
  }

  return {
    specs,
    denCandidates: parsePositiveIntCsv(tilingDenCandidates.value),
    coeffCandidates: parsePositiveIntCsv(tilingCoeffCandidates.value),
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
      const n = normalizePoint("side", center.x, center.y);
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
  sourceMode.value = "designer";
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

async function loadPresetCpGraph(): Promise<void> {
  busy.value = true;
  errorMessage.value = "";
  try {
    const res = await fetch(selectedPresetPath.value, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`http ${res.status}`);
    }
    const payload = (await res.json()) as CpGraphV1Json;
    externalCorners.value = cornersFromCpGraph(payload);
    externalSourceLabel.value = `preset: ${selectedPresetPath.value}`;
    sourceMode.value = "external";
    evaluations.value = [];
    bestProfileName.value = "";
    selectedProfileName.value = "";
    previewResult.value = null;
    previewProfileName.value = "";
  } catch (err) {
    errorMessage.value = `preset load failed: ${err instanceof Error ? err.message : String(err)}`;
  } finally {
    busy.value = false;
  }
}

async function onImportCpGraph(ev: Event): Promise<void> {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  try {
    const text = await file.text();
    const payload = JSON.parse(text) as CpGraphV1Json;
    externalCorners.value = cornersFromCpGraph(payload);
    externalSourceLabel.value = `cp_graph: ${file.name}`;
    sourceMode.value = "external";
    evaluations.value = [];
    bestProfileName.value = "";
    selectedProfileName.value = "";
    previewResult.value = null;
    previewProfileName.value = "";
    errorMessage.value = "";
  } catch (err) {
    errorMessage.value = `import failed: ${err instanceof Error ? err.message : String(err)}`;
  } finally {
    input.value = "";
  }
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
          <h1>Origami Engine Lab</h1>
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
          <button class="btn ghost" :disabled="busy" @click="runTilingFromDesigner">{{ tr("タイリング", "Tiling") }}</button>
          <button class="btn" :disabled="busy" @click="runProfiles">{{ tr("展開図生成", "Run") }}</button>
          <button class="btn ghost" :disabled="busy || !selectedEvaluation" @click="runPreviewForSelectedProfile">
            {{ tr("折り上がり", "Preview") }}
          </button>
        </div>
      </div>
    </section>

    <section class="panel designer">
      <h2>{{ tr("カド配置キャンバス", "Corner Layout Canvas") }}</h2>
      <div class="designer-top">
        <label class="check">
          <input v-model="symmetryEnabled" type="checkbox" />
          {{ tr("y = x 対称", "y = x symmetry") }}
        </label>
        <label class="check">
          <input v-model="showDesignerGrid" type="checkbox" />
          {{ tr("格子点を表示", "show grid points") }}
        </label>
        <label>
          a
          <input v-model.number="aMaxInput" type="number" min="1" max="24" />
        </label>
        <label>
          b
          <input v-model.number="bMaxInput" type="number" min="1" max="24" />
        </label>
        <label>
          k
          <input v-model.number="kMaxInput" type="number" min="1" max="8" />
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
      <div class="designer-grid">
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
            v-if="symmetryEnabled"
            x1="0"
            :y1="CANVAS_SIZE"
            :x2="CANVAS_SIZE"
            y2="0"
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
              v-for="p in sidePoints"
              :key="`mirror_${p.id}`"
              :cx="toCanvasX(p.y)"
              :cy="toCanvasY(p.x)"
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
        <div class="designer-side">
          <p v-if="canvasEditMode === 'point'" class="tip">{{ tr("クリックで追加、ドラッグで移動。点は (a+b√2)/2^k 格子へ吸着します。", "Click to add and drag to move. Points snap to the (a+b*sqrt(2))/2^k lattice.") }}</p>
          <p v-else class="tip">{{ tr("初期辺編集: 角点/格子点を2回クリック、またはドラッグで始点→終点を指定してください。", "Seed-edge edit: click corner/grid points twice, or drag start to end.") }}</p>
          <p v-if="canvasEditMode === 'edge' && edgeDraftStartPick">
            {{ tr("始点", "start") }}:
            <span v-if="edgeDraftStartPick.cornerIdx !== null">#{{ edgeDraftStartPick.cornerIdx }}</span>
            <span v-else>({{ edgeDraftStartPick.x.toFixed(3) }}, {{ edgeDraftStartPick.y.toFixed(3) }})</span>
          </p>
          <p>{{ tr("現在のカド数（境界込み）", "Current corner count (with boundary)") }}: {{ activeCorners.length }}</p>
          <p>{{ tr("使用ソース", "Source") }}: {{ sourceLabel }}</p>
          <p v-if="symmetryEnabled">{{ tr("Axis", "Axis") }}: {{ axisPoints.length }} / {{ tr("Side（片側）", "Side (one side)") }}: {{ sidePoints.length }}</p>
          <p v-else>{{ tr("Free", "Free") }}: {{ freePoints.length }}</p>
          <div class="row-btn">
            <button class="btn ghost" :disabled="busy" @click="clearDesignerInteriorPoints">{{ tr("内部点をクリア", "Clear interior points") }}</button>
            <button class="btn ghost" :disabled="busy" @click="resetDesignerDefaults">{{ tr("既定値に戻す", "Reset defaults") }}</button>
          </div>
          <div v-if="selectedMeta && canvasEditMode === 'point'" class="selected-editor">
            <h3>{{ tr("選択中の点", "Selected point") }}</h3>
            <p>{{ tr("グループ", "Group") }}: {{ selectedMeta.group }} / id: {{ selectedMeta.point.id }}</p>
            <label>
              x
              <input
                :value="selectedMeta.point.x"
                type="number"
                min="0"
                max="1"
                :step="latticeStep"
                @input="updateSelectedCoord('x', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label>
              y
              <input
                :value="selectedMeta.point.y"
                type="number"
                min="0"
                max="1"
                :step="latticeStep"
                @input="updateSelectedCoord('y', ($event.target as HTMLInputElement).value)"
              />
            </label>
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
        </div>
      </div>
    </section>

    <section class="panel tiling-panel">
      <h2>{{ tr("タイリング最適化", "Tiling Optimization") }}</h2>
      <div class="tiling-row">
        <label>
          seed
          <input v-model.number="tilingSeed" type="number" step="1" />
        </label>
        <label>
          den candidates
          <input v-model="tilingDenCandidates" type="text" />
        </label>
        <label>
          coeff candidates
          <input v-model="tilingCoeffCandidates" type="text" />
        </label>
        <label>
          alpha steps
          <input v-model.number="tilingAlphaSteps" type="number" min="1" max="64" />
        </label>
        <label>
          pack restarts
          <input v-model.number="tilingPackRestarts" type="number" min="1" max="200" />
        </label>
        <label>
          pack iters
          <input v-model.number="tilingPackIters" type="number" min="1" max="5000" />
        </label>
      </div>
      <div class="row-btn">
        <button class="btn" :disabled="busy" @click="runTilingFromDesigner">
          {{ tr("タイリング実行（成功時に点を置換）", "Run Tiling (replace points on success)") }}
        </button>
      </div>
      <p class="tip">{{ tr("成功すると、初期点は削除され、最適化後の中心点がこのキャンバスに反映されます。", "On success, initial points are removed and replaced by optimized centers in the same canvas.") }}</p>
      <p v-if="tilingState">
        tiling: {{ tilingState.ok ? "ok" : "ng" }},
        alpha={{ tilingState.alpha.toFixed(4) }},
        den={{ tilingState.den }},
        coeff={{ tilingState.coeffLimit }},
        cornerHits={{ tilingState.cornerHits }},
        contact={{ tilingState.contactScore.toFixed(3) }}
      </p>
    </section>

    <section class="panel controls">
      <h2>{{ tr("展開図生成", "Crease Generation") }}</h2>
      <div class="corner-source-box">
        <h3>{{ tr("展開図生成に使うカド", "Corners used for crease generation") }}</h3>
        <p>{{ tr("現在のソース", "Current source") }}: {{ sourceLabel }}</p>
        <p>{{ tr("カド数", "Corner count") }}: {{ activeCorners.length }}</p>
        <details>
          <summary>{{ tr("カド一覧を表示", "Show corner list") }}</summary>
          <ul class="corner-list">
            <li v-for="row in activeCornerRows" :key="`active_corner_${row.idx}`">
              #{{ row.idx }}: {{ row.approx }} / {{ row.exact }}
            </li>
          </ul>
        </details>
      </div>
      <div class="seed-edge-box">
        <h3>{{ tr("探索予算", "Search budget") }}</h3>
        <div class="seed-edge-row">
          <label>
            {{ tr("max depth", "max depth") }}
            <input v-model.number="searchMaxDepthInput" class="tiny-num" type="number" min="1" max="64" step="1" />
          </label>
          <label>
            {{ tr("branch/node", "branch/node") }}
            <input v-model.number="searchBranchPerNodeInput" class="tiny-num" type="number" min="1" max="64" step="1" />
          </label>
          <label>
            {{ tr("max nodes", "max nodes") }}
            <input v-model.number="searchMaxNodesInput" class="tiny-num" type="number" min="1" max="200000" step="1" />
          </label>
          <label>
            allowViolations
            <input v-model.number="searchAllowViolationsInput" class="tiny-num" type="number" min="0" max="64" step="1" />
          </label>
          <label>
            dirTopK
            <input v-model.number="searchDirTopKInput" class="tiny-num" type="number" min="1" max="16" step="1" />
          </label>
          <label>
            priorityTopN
            <input v-model.number="searchPriorityTopNInput" class="tiny-num" type="number" min="1" max="32" step="1" />
          </label>
        </div>
        <p class="tip seed-edge-tip">
          {{ tr("大きくすると探索は強くなりますが、計算時間も伸びます。", "Larger values strengthen search but increase runtime.") }}
        </p>
      </div>
      <div class="seed-edge-box">
        <h3>{{ tr("初期辺（任意）", "Initial seed edges (optional)") }}</h3>
        <div class="seed-edge-row">
          <label class="check">
            <input
              v-model="seedEdgeAutoMirror"
              type="checkbox"
              :disabled="busy || !symmetryEnabled"
            />
            {{ tr("y=x で自動ミラー", "auto mirror by y=x") }}
          </label>
          <label>
            {{ tr("corner i", "corner i") }}
            <select v-model.number="seedEdgeI" class="mini-select" :disabled="busy || activeCorners.length <= 1">
              <option v-for="opt in cornerOptions" :key="`seed_i_${opt.idx}`" :value="opt.idx">
                {{ opt.label }}
              </option>
            </select>
          </label>
          <label>
            {{ tr("corner j", "corner j") }}
            <select v-model.number="seedEdgeJ" class="mini-select" :disabled="busy || activeCorners.length <= 1">
              <option v-for="opt in cornerOptions" :key="`seed_j_${opt.idx}`" :value="opt.idx">
                {{ opt.label }}
              </option>
            </select>
          </label>
          <button class="btn ghost" :disabled="busy || activeCorners.length <= 1" @click="addSeedEdge">
            {{ tr("辺を追加", "Add edge") }}
          </button>
          <button class="btn ghost" :disabled="busy || seedEdges.length <= 0" @click="clearSeedEdges">
            {{ tr("クリア", "Clear") }}
          </button>
        </div>
        <p class="tip seed-edge-tip">
          {{ tr("実行時の辺数", "Run edges") }}: {{ seedEdgesForRun.length }}
          <span v-if="seedEdgeAutoAddedCount > 0"> {{ tr("(ミラー追加 +", "(mirrored +") }}{{ seedEdgeAutoAddedCount }})</span>
        </p>
        <ul v-if="seedEdges.length > 0" class="seed-edge-list">
          <li v-for="(edge, idx) in seedEdges" :key="`seed_edge_${edge.cornerI}_${edge.cornerJ}`">
            <span>{{ idx + 1 }}. {{ cornerLabel(edge.cornerI) }} - {{ cornerLabel(edge.cornerJ) }}</span>
            <button class="btn danger mini" :disabled="busy" @click="removeSeedEdgeAt(idx)">{{ tr("削除", "Remove") }}</button>
          </li>
        </ul>
        <p v-else class="empty">{{ tr("初期辺はありません。", "No seed edge.") }}</p>

        <h3 class="seed-subtitle">{{ tr("格子セグメント（厳密、任意）", "Grid seed segments (exact, optional)") }}</h3>
        <div class="seed-edge-row">
          <label class="check">
            <input
              v-model="seedSegmentAutoMirror"
              type="checkbox"
              :disabled="busy || !symmetryEnabled"
            />
            {{ tr("y=x で自動ミラー", "auto mirror by y=x") }}
          </label>
        </div>
        <div class="seed-segment-grid">
          <label>
            from x (a,b,k)
            <input v-model.number="seedSegmentDraft.fromXa" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.fromXb" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.fromXk" class="tiny-num" type="number" min="0" step="1" />
          </label>
          <label>
            from y (a,b,k)
            <input v-model.number="seedSegmentDraft.fromYa" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.fromYb" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.fromYk" class="tiny-num" type="number" min="0" step="1" />
          </label>
          <label>
            to x (a,b,k)
            <input v-model.number="seedSegmentDraft.toXa" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.toXb" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.toXk" class="tiny-num" type="number" min="0" step="1" />
          </label>
          <label>
            to y (a,b,k)
            <input v-model.number="seedSegmentDraft.toYa" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.toYb" class="tiny-num" type="number" step="1" />
            <input v-model.number="seedSegmentDraft.toYk" class="tiny-num" type="number" min="0" step="1" />
          </label>
        </div>
        <div class="seed-edge-row">
          <button class="btn ghost" :disabled="busy" @click="addSeedSegmentFromDraft">{{ tr("セグメント追加", "Add segment") }}</button>
          <button class="btn ghost" :disabled="busy || seedSegments.length <= 0" @click="clearSeedSegments">
            {{ tr("セグメントをクリア", "Clear segments") }}
          </button>
        </div>
        <p class="tip seed-edge-tip">
          {{ tr("実行時のセグメント数", "Run segments") }}: {{ seedSegmentsForRun.length }}
          <span v-if="seedSegmentAutoAddedCount > 0"> {{ tr("(ミラー追加 +", "(mirrored +") }}{{ seedSegmentAutoAddedCount }})</span>
        </p>
        <ul v-if="seedSegments.length > 0" class="seed-edge-list">
          <li v-for="(seg, idx) in seedSegments" :key="`seed_segment_${idx}`">
            <span>
              {{ idx + 1 }}. {{ seedSegmentLabel(seg) }} / {{ pointExactLabel(seg.from) }} ->
              {{ pointExactLabel(seg.to) }}
            </span>
            <button class="btn danger mini" :disabled="busy" @click="removeSeedSegmentAt(idx)">{{ tr("削除", "Remove") }}</button>
          </li>
        </ul>
        <p v-else class="empty">{{ tr("初期セグメントはありません。", "No seed segment.") }}</p>
      </div>
      <div class="control-row">
        <button class="btn" :disabled="busy" @click="runProfiles">{{ tr("展開図生成を実行", "Run crease generation") }}</button>
        <select v-model="selectedPresetPath" class="select" :disabled="busy">
          <option v-for="preset in PRESET_CP_GRAPHS" :key="preset.path" :value="preset.path">
            {{ preset.label }}
          </option>
        </select>
        <button class="btn ghost" :disabled="busy" @click="loadPresetCpGraph">{{ tr("プリセット読込", "Load preset") }}</button>
        <label class="file-label">
          {{ tr("cp_graph_v1 JSON 読込", "Import cp_graph_v1 JSON") }}
          <input type="file" accept=".json,application/json" :disabled="busy" @change="onImportCpGraph" />
        </label>
      </div>
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

    <section class="panel result">
      <h2>Evaluation Result</h2>
      <div v-if="evaluations.length > 0" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Profile</th>
              <th>Corner</th>
              <th>Kawasaki</th>
              <th>Priority K</th>
              <th>Edge</th>
              <th>Vertex</th>
              <th>Recurse</th>
              <th>Refresh A/T</th>
              <th>FinalPrune R/E</th>
              <th>Sec</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="ev in evaluations"
              :key="ev.profile.name"
              :class="{
                bestRow: ev.profile.name === bestProfileName,
                activeRow: ev.profile.name === selectedEvaluation?.profile.name,
              }"
              @click="selectProfileForPreview(ev.profile.name)"
            >
              <td>{{ ev.profile.name }}</td>
              <td>{{ ev.summary.cornerViolationsAfter }}</td>
              <td>{{ ev.summary.kawasakiViolationsAfter }}</td>
              <td>{{ ev.summary.priorityCornerKawasakiViolationsAfter }}</td>
              <td>{{ ev.summary.edgeCount }}</td>
              <td>{{ ev.summary.vertexCount }}</td>
              <td>{{ num(ev.summary.recurseCalls) }}</td>
              <td>{{ num(ev.summary.refreshApplied) }} / {{ num(ev.summary.refreshTrigger) }}</td>
              <td>{{ num(ev.summary.finalPruneAppliedRounds) }} / {{ num(ev.summary.finalPruneRemovedEdges) }}</td>
              <td>{{ ev.summary.sec.toFixed(3) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="empty">No run yet.</p>
    </section>

    <section class="panel status-strip">
      <div class="meta-row">
        <span>{{ tr("状態", "Status") }}: {{ busy ? tr("実行中", "Running") : tr("待機", "Ready") }}</span>
        <span>{{ tr("ソース", "Source") }}: {{ sourceLabel }}</span>
        <span>{{ tr("モード", "Mode") }}: {{ sourceMode }}</span>
        <span>{{ tr("カド数", "Corner count") }}: {{ activeCorners.length }}</span>
        <span>{{ tr("初期辺 raw/run", "Seed edges raw/run") }}: {{ seedEdges.length }} / {{ seedEdgesForRun.length }}</span>
        <span>{{ tr("初期セグメント raw/run", "Seed segments raw/run") }}: {{ seedSegments.length }} / {{ seedSegmentsForRun.length }}</span>
        <span>{{ tr("格子 a,b,k", "Grid a,b,k") }}: {{ clampInt(aMaxInput, 1, 24) }}, {{ clampInt(bMaxInput, 1, 24) }}, {{ clampInt(kMaxInput, 1, 8) }}</span>
        <span>budget: d={{ clampInt(searchMaxDepthInput, 1, 64) }}, b={{ clampInt(searchBranchPerNodeInput, 1, 64) }}, n={{ clampInt(searchMaxNodesInput, 1, 200000) }}</span>
        <span v-if="lastRunAt">{{ tr("最終実行", "Last run") }}: {{ lastRunAt }}</span>
      </div>
      <div class="progress-wrap compact">
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${Math.round(progressRatio * 100)}%` }"></div>
        </div>
        <div class="progress-text">
          <span>{{ Math.round(progressRatio * 100) }}%</span>
          <span>{{ progressStage }}</span>
          <span>{{ progressMessage }}</span>
          <span v-if="bestProfileName">Best: {{ bestProfileName }}</span>
        </div>
      </div>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </section>
  </main>
</template>

