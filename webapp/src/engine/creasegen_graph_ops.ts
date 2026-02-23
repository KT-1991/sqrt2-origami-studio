import type { PointE } from "./types";
import { PAPER_MAX_Q, PAPER_MIN_Q } from "./paper_frame";
import { enumerateGridPoints, GridCreaseGraph } from "./creasegen_graph";
import { pointKLevel, pointKey, recordMissingPointStats } from "./creasegen_grid_utils";

function point(x: PointE["x"], y: PointE["y"]): PointE {
  return { x, y };
}

export function cloneGraph(g: GridCreaseGraph): GridCreaseGraph {
  return g.cloneSharedBase();
}

export function adoptGraphState(dst: GridCreaseGraph, src: GridCreaseGraph): void {
  dst.copyMutableStateFrom(src);
}

export function graphStateKey(g: GridCreaseGraph): [bigint, bigint, number] {
  return g.stateKey();
}

export interface MakeGridGraphOptions {
  corners: ReadonlyArray<PointE>;
  initialCornerEdgePairs?: ReadonlyArray<{
    cornerI: number;
    cornerJ: number;
  }>;
  initialSegments?: ReadonlyArray<{
    from: PointE;
    to: PointE;
  }>;
  aMax: number;
  bMax: number;
  kMax: number;
  cornerMaxDeg?: number;
  minCornerLines?: number;
  enforceSymmetry?: boolean;
  useLocalRayDirty?: boolean;
  seedStats?: Record<string, number>;
  seedDirectCornerConnections: (
    g: GridCreaseGraph,
    cornerIds: number[],
    opts: {
      maxDeg: number;
      minCornerLines: number;
      enforceSymmetry: boolean;
      stats?: Record<string, number>;
    },
  ) => void;
  addSegmentWithSplitsIds: (
    g: GridCreaseGraph,
    startV: number,
    goalV: number,
    opts: {
      maxSteps: number;
      stats?: Record<string, number>;
    },
  ) => boolean;
}

export function makeGridGraph(opts: MakeGridGraphOptions): {
  graph: GridCreaseGraph;
  cornerIds: number[];
} {
  const { points, p2i } = enumerateGridPoints(opts.aMax, opts.bMax, opts.kMax);
  const g = new GridCreaseGraph({
    points,
    p2i,
    useLocalRayDirty: opts.useLocalRayDirty ?? false,
  });
  g.initSquareBoundary();
  const cornerIds = opts.corners.map((p) => g.addVertex(p));

  if (opts.initialCornerEdgePairs && opts.initialCornerEdgePairs.length > 0) {
    const seen = new Set<string>();
    for (const pair of opts.initialCornerEdgePairs) {
      const i = pair.cornerI;
      const j = pair.cornerJ;
      if (!Number.isInteger(i) || !Number.isInteger(j)) {
        opts.seedStats = opts.seedStats ?? {};
        opts.seedStats.initial_seed_edge_invalid =
          (opts.seedStats.initial_seed_edge_invalid ?? 0) + 1;
        continue;
      }
      if (i < 0 || j < 0 || i >= cornerIds.length || j >= cornerIds.length || i === j) {
        opts.seedStats = opts.seedStats ?? {};
        opts.seedStats.initial_seed_edge_invalid =
          (opts.seedStats.initial_seed_edge_invalid ?? 0) + 1;
        continue;
      }
      const a = i < j ? i : j;
      const b = i < j ? j : i;
      const key = `${a},${b}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      opts.seedStats = opts.seedStats ?? {};
      opts.seedStats.initial_seed_edge_attempt =
        (opts.seedStats.initial_seed_edge_attempt ?? 0) + 1;
      const ok = opts.addSegmentWithSplitsIds(g, cornerIds[a], cornerIds[b], {
        maxSteps: 128,
        stats: opts.seedStats,
      });
      if (ok) {
        opts.seedStats.initial_seed_edge_applied =
          (opts.seedStats.initial_seed_edge_applied ?? 0) + 1;
      } else {
        opts.seedStats.initial_seed_edge_failed =
          (opts.seedStats.initial_seed_edge_failed ?? 0) + 1;
      }
    }
  }

  if (opts.initialSegments && opts.initialSegments.length > 0) {
    const seen = new Set<string>();
    for (const seg of opts.initialSegments) {
      const fromKey = pointKey(seg.from);
      const toKey = pointKey(seg.to);
      if (fromKey === toKey) {
        opts.seedStats = opts.seedStats ?? {};
        opts.seedStats.initial_seed_segment_invalid =
          (opts.seedStats.initial_seed_segment_invalid ?? 0) + 1;
        continue;
      }
      const key = fromKey < toKey ? `${fromKey}|${toKey}` : `${toKey}|${fromKey}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      opts.seedStats = opts.seedStats ?? {};
      opts.seedStats.initial_seed_segment_attempt =
        (opts.seedStats.initial_seed_segment_attempt ?? 0) + 1;
      let startV = -1;
      let goalV = -1;
      try {
        startV = g.addVertex(seg.from);
        goalV = g.addVertex(seg.to);
      } catch {
        opts.seedStats.initial_seed_segment_missing_point =
          (opts.seedStats.initial_seed_segment_missing_point ?? 0) + 1;
        recordMissingPointStats(opts.seedStats, seg.from);
        recordMissingPointStats(opts.seedStats, seg.to);
        continue;
      }
      const ok = opts.addSegmentWithSplitsIds(g, startV, goalV, {
        maxSteps: 128,
        stats: opts.seedStats,
      });
      if (ok) {
        opts.seedStats.initial_seed_segment_applied =
          (opts.seedStats.initial_seed_segment_applied ?? 0) + 1;
      } else {
        opts.seedStats.initial_seed_segment_failed =
          (opts.seedStats.initial_seed_segment_failed ?? 0) + 1;
      }
    }
  }

  opts.seedDirectCornerConnections(g, cornerIds, {
    maxDeg: opts.cornerMaxDeg ?? 45.0,
    minCornerLines: opts.minCornerLines ?? 2,
    enforceSymmetry: opts.enforceSymmetry ?? true,
    stats: opts.seedStats,
  });

  const v00 = g.addVertex(point(PAPER_MIN_Q, PAPER_MIN_Q));
  const v11 = g.addVertex(point(PAPER_MAX_Q, PAPER_MAX_Q));
  opts.addSegmentWithSplitsIds(g, v00, v11, {
    maxSteps: 128,
    stats: opts.seedStats,
  });
  g.recomputeRayNextAll();
  return { graph: g, cornerIds };
}

export function graphStats(g: GridCreaseGraph): {
  grid_points_total: number;
  active_vertices: number;
  edges: number;
  max_k_active: number;
} {
  let maxK = -1;
  for (const v of g.activeVertices) {
    const k = pointKLevel(g.points[v]);
    maxK = Math.max(maxK, k);
  }
  return {
    grid_points_total: g.points.length,
    active_vertices: g.activeVertices.size,
    edges: g.edges.size,
    max_k_active: maxK,
  };
}

export function remapGraphToNewGrid(src: GridCreaseGraph, dst: GridCreaseGraph): void {
  const vmap = new Map<number, number>();
  for (const v of src.activeVertices) {
    const nv = dst.pointToId.get(pointKey(src.points[v]));
    if (nv === undefined) {
      continue;
    }
    dst.activateVertex(nv);
    vmap.set(v, nv);
  }
  for (const [i, j] of src.edgePairs()) {
    const ni = vmap.get(i);
    const nj = vmap.get(j);
    if (ni === undefined || nj === undefined || ni === nj) {
      continue;
    }
    const boundary = src.boundaryEdges.has(`${Math.min(i, j)},${Math.max(i, j)}`);
    dst.addEdge(ni, nj, boundary);
  }
  for (const v of dst.activeVertices) {
    dst.rayDirty.add(v);
  }
}

function absBigintToSafeInt(x: bigint): number {
  const n = Number(x < 0n ? -x : x);
  return Number.isSafeInteger(n) ? n : Number.MAX_SAFE_INTEGER;
}

export function latticeBoundsActive(g: GridCreaseGraph): {
  max_k: number;
  max_abs_a: number;
  max_abs_b: number;
} {
  let maxK = -1;
  let maxAbsA = 0;
  let maxAbsB = 0;
  for (const v of g.activeVertices) {
    const p = g.points[v];
    for (const z of [p.x, p.y]) {
      maxK = Math.max(maxK, z.k);
      maxAbsA = Math.max(maxAbsA, absBigintToSafeInt(z.a));
      maxAbsB = Math.max(maxAbsB, absBigintToSafeInt(z.b));
    }
  }
  return {
    max_k: maxK,
    max_abs_a: maxAbsA,
    max_abs_b: maxAbsB,
  };
}
