/*
  Canonical runtime and persistence contracts for TS migration.
  Runtime models are used in hot path (in-memory).
  Persistence models are JSON-safe for import/export.
*/

export type StageId = "tiling" | "creasegen" | "preview";

export interface EngineProgressEvent {
  kind: "progress";
  requestId: string;
  stage: StageId;
  ratio: number; // 0.0 - 1.0
  message?: string;
}

export interface EngineErrorEvent {
  kind: "error";
  requestId: string;
  stage: StageId;
  code:
    | "INVALID_INPUT"
    | "UNSUPPORTED_SCHEMA"
    | "NUMERIC_DOMAIN"
    | "SEARCH_EXHAUSTED"
    | "INTERNAL";
  message: string;
  detail?: Record<string, unknown>;
}

export interface EngineResultEvent<T> {
  kind: "result";
  requestId: string;
  stage: StageId;
  payload: T;
}

export interface EngineRunRequest<T> {
  kind: "run";
  requestId: string;
  stage: StageId;
  payload: T;
}

/* =========================
   Exact numeric primitives
   ========================= */

// Represents (a + b*sqrt(2)) / 2^k.
export interface Qsqrt2 {
  a: bigint;
  b: bigint;
  k: number;
}

export interface PointE {
  x: Qsqrt2;
  y: Qsqrt2;
}

export interface Vec2 {
  x: number;
  y: number;
}

/* =========================
   Stage A: Tiling
   ========================= */

export type KadoSymmetry = "axis" | "pair";

export interface KadoSpec {
  name: string;
  length: number;
  symmetry: KadoSymmetry;
  pairName?: string;
}

// UI-friendly input: tuning fields are optional and resolved with defaults.
export interface TilingRunInput {
  specs: KadoSpec[];
  denCandidates?: number[];
  coeffCandidates?: number[];
  seed?: number;
  alphaSteps?: number;
  packRestarts?: number;
  packIters?: number;
  packGuidedRestarts?: number;
  packGuidedJitter?: number;
  warmStart?: boolean;
  initialCenters?: Record<string, Vec2>;
  initialIndependent?: Record<string, Vec2>;
}

export interface TilingRunInputResolved {
  specs: KadoSpec[];
  denCandidates: number[];
  coeffCandidates: number[];
  seed: number;
  alphaSteps: number;
  packRestarts: number;
  packIters: number;
  packGuidedRestarts: number;
  packGuidedJitter: number;
  warmStart: boolean;
  initialCenters?: Record<string, Vec2>;
  initialIndependent?: Record<string, Vec2>;
}

export const DEFAULT_TILING_OPTIONS: Omit<
  TilingRunInputResolved,
  "specs" | "initialCenters" | "initialIndependent"
> = {
  denCandidates: [1, 2],
  coeffCandidates: [1, 2],
  seed: 0,
  alphaSteps: 14,
  packRestarts: 10,
  packIters: 700,
  packGuidedRestarts: 3,
  packGuidedJitter: 0.08,
  warmStart: true,
};

export interface TilingState {
  ok: boolean;
  alpha: number;
  den: number;
  coeffLimit: number;
  centers: Record<string, Vec2>;
  cornerHits: number;
  contactScore: number;
  message: string;
}

/* =========================
   Stage B: Creasegen
   ========================= */

// Fully resolved runtime config (mirrors python defaults in run_config.py).
export interface RunConfig {
  aMax: number;
  bMax: number;
  kMax: number;
  cornerMaxDeg: number;
  maxDepth: number;
  branchPerNode: number;
  allowViolations: number;
  maxNodes: number;
  enforceSymmetry: boolean;
  enableOpenSink: boolean;
  enableOpenSinkRepair: boolean;
  openSinkMaxBounces: number;
  minCornerLines: number;
  kawasakiTol: number;
  enableCornerKawasakiRepair: boolean;
  enableTriangleMacro: boolean;
  requireCornerKawasaki: boolean;
  stagedKRelax: boolean;
  kStart: number;
  dirTopK: number;
  priorityTopN: number;
  useLocalRayDirty: boolean;
  stopOnCornerClear: boolean;
  autoExpandGrid: boolean;
  autoExpandMaxRounds: number;
  expandStallRounds: number;
  seedAutoExpand: boolean;
  seedAutoExpandMaxRounds: number;
  finalPrune: boolean;
  finalPruneRounds: number;
  finalPruneMaxCandidates: number;
  showPruneAxes: boolean;
  pruneAxesMax: number;
  showOrder: boolean;
  highlightKawasaki: boolean;
  draftGuided: boolean;
  draftMaxDepth: number;
  draftBranchPerNode: number;
  draftMaxNodes: number;
}

// UI-friendly partial input. Resolve with DEFAULT_RUN_CONFIG before execution.
export type RunConfigInput = Partial<RunConfig>;

export const DEFAULT_RUN_CONFIG: RunConfig = {
  aMax: 2,
  bMax: 2,
  kMax: 2,
  cornerMaxDeg: 45.0,
  maxDepth: 6,
  branchPerNode: 4,
  allowViolations: 2,
  maxNodes: 300,
  enforceSymmetry: true,
  enableOpenSink: true,
  enableOpenSinkRepair: true,
  openSinkMaxBounces: 14,
  minCornerLines: 2,
  kawasakiTol: 1e-8,
  enableCornerKawasakiRepair: true,
  enableTriangleMacro: false,
  requireCornerKawasaki: true,
  stagedKRelax: false,
  kStart: 1,
  dirTopK: 4,
  priorityTopN: 6,
  useLocalRayDirty: false,
  stopOnCornerClear: false,
  autoExpandGrid: false,
  autoExpandMaxRounds: 3,
  expandStallRounds: 1,
  seedAutoExpand: true,
  seedAutoExpandMaxRounds: 1,
  finalPrune: true,
  finalPruneRounds: 2,
  finalPruneMaxCandidates: 64,
  showPruneAxes: false,
  pruneAxesMax: 24,
  showOrder: false,
  highlightKawasaki: false,
  draftGuided: false,
  draftMaxDepth: 1,
  draftBranchPerNode: 2,
  draftMaxNodes: 80,
};

export interface CreaseBuildInput {
  corners: PointE[];
  seedEdges?: CreaseSeedEdgeInput[];
  seedSegments?: CreaseSeedSegmentInput[];
  config?: RunConfigInput;
  tiling?: TilingState;
}

export interface CreaseSeedEdgeInput {
  cornerI: number;
  cornerJ: number;
}

export interface CreaseSeedSegmentInput {
  from: PointE;
  to: PointE;
}

export interface MemVertex {
  id: number;
  point: PointE;
  pointApprox: Vec2;
  isCorner: boolean;
  isBoundary: boolean;
}

export interface MemEdge {
  id: number;
  v0: number;
  v1: number;
  isBoundary: boolean;
  axis8: number;
  birthOrder: number;
}

export interface CreaseGraphMem {
  schema: "cp_graph_mem_v1";
  vertices: MemVertex[];
  edges: MemEdge[];
  corners: number[];
  stats: {
    vertexCount: number;
    edgeCount: number;
    boundaryEdgeCount: number;
    cornerCount: number;
  };
  params?: Record<string, unknown>;
  searchStats?: Record<string, number>;
  stageLogs?: Array<Record<string, unknown>>;
}

export interface CreaseRunResult {
  sec: number;
  graph: CreaseGraphMem;
  metrics: {
    cornerViolationsAfter: number;
    kawasakiViolationsAfter: number;
    priorityCornerKawasakiViolationsAfter: number;
  };
}

/* =========================
   Stage C: Fold preview
   ========================= */

export interface FoldPreviewInput {
  graph: CreaseGraphMem;
  alpha: number;
  lineWidth: number;
  showFaceId: boolean;
}

export interface FacePolygon {
  faceId: number;
  points: Vec2[];
  depth: number;
  frontSide: boolean;
}

export interface FoldPreviewResult {
  facePolygons: FacePolygon[];
  stats: {
    segmentCount: number;
    faceCount: number;
    dualEdgeCount: number;
    transformInconsistencies: number;
  };
}

/* =========================
   Persistence (JSON-safe)
   ========================= */

export interface CpGraphV1Json {
  schema: "cp_graph_v1";
  domain: {
    shape: "unit_square";
    x_min: number;
    x_max: number;
    y_min: number;
    y_max: number;
  };
  direction: {
    dir_count: 16;
    axis_count: 8;
  };
  vertices: Array<{
    id: number;
    point: {
      x: { a: number; b: number; k: number };
      y: { a: number; b: number; k: number };
      x_approx: number;
      y_approx: number;
    };
    is_corner: boolean;
    is_boundary: boolean;
  }>;
  edges: Array<{
    id: number;
    v0: number;
    v1: number;
    is_boundary: boolean;
    axis8: number;
    birth_order: number;
  }>;
  corners: number[];
  stats: {
    vertex_count: number;
    edge_count: number;
    boundary_edge_count: number;
    corner_count: number;
  };
  params: Record<string, unknown> | null;
  search_stats: Record<string, number> | null;
  stage_logs: Array<Record<string, unknown>> | null;
}

export interface ProjectFileV1 {
  schema: "origami_project_v1";
  createdAtIso: string;
  tilingInput: TilingRunInput;
  tilingState?: TilingState;
  creaseInput?: CreaseBuildInput;
  cpGraph?: CpGraphV1Json;
  previewOptions?: Omit<FoldPreviewInput, "graph">;
}

/* =========================
   Engine facade
   ========================= */

export interface OrigamiEngine {
  runTiling(input: TilingRunInput): Promise<TilingState>;
  runCreasegen(input: CreaseBuildInput): Promise<CreaseRunResult>;
  runPreview(input: FoldPreviewInput): Promise<FoldPreviewResult>;
  runAll(input: {
    tiling: TilingRunInput;
    creaseConfig?: RunConfigInput;
    preview: Omit<FoldPreviewInput, "graph">;
    corners: PointE[];
  }): Promise<{
    tiling: TilingState;
    crease: CreaseRunResult;
    preview: FoldPreviewResult;
  }>;
}
