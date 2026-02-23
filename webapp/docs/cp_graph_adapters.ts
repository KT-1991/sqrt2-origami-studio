import {
  CpGraphV1Json,
  CreaseGraphMem,
  PointE,
  Qsqrt2,
  Vec2,
} from "./engine_types";

const DEFAULT_DOMAIN: CpGraphV1Json["domain"] = {
  shape: "unit_square",
  x_min: 0.0,
  x_max: 1.0,
  y_min: 0.0,
  y_max: 1.0,
};

const DEFAULT_DIRECTION: CpGraphV1Json["direction"] = {
  dir_count: 16,
  axis_count: 8,
};

function bigintFromSafeInt(value: number, field: string): bigint {
  if (!Number.isSafeInteger(value)) {
    throw new Error(`${field} must be a safe integer`);
  }
  return BigInt(value);
}

function numberFromBigint(value: bigint, field: string): number {
  const n = Number(value);
  if (!Number.isSafeInteger(n)) {
    throw new Error(`${field} is outside JS safe integer range`);
  }
  return n;
}

export function qsqrt2FromJson(
  z: { a: number; b: number; k: number },
  field: string,
): Qsqrt2 {
  if (!Number.isInteger(z.k) || z.k < 0) {
    throw new Error(`${field}.k must be a non-negative integer`);
  }
  return {
    a: bigintFromSafeInt(z.a, `${field}.a`),
    b: bigintFromSafeInt(z.b, `${field}.b`),
    k: z.k,
  };
}

export function qsqrt2ToJson(
  z: Qsqrt2,
  field: string,
): { a: number; b: number; k: number } {
  if (!Number.isInteger(z.k) || z.k < 0) {
    throw new Error(`${field}.k must be a non-negative integer`);
  }
  return {
    a: numberFromBigint(z.a, `${field}.a`),
    b: numberFromBigint(z.b, `${field}.b`),
    k: z.k,
  };
}

export function pointEFromJson(
  p: { x: { a: number; b: number; k: number }; y: { a: number; b: number; k: number } },
  field: string,
): PointE {
  return {
    x: qsqrt2FromJson(p.x, `${field}.x`),
    y: qsqrt2FromJson(p.y, `${field}.y`),
  };
}

export function pointEToJson(
  p: PointE,
  field: string,
): { x: { a: number; b: number; k: number }; y: { a: number; b: number; k: number } } {
  return {
    x: qsqrt2ToJson(p.x, `${field}.x`),
    y: qsqrt2ToJson(p.y, `${field}.y`),
  };
}

export function cpGraphV1ToMemGraph(payload: CpGraphV1Json): CreaseGraphMem {
  if (payload.schema !== "cp_graph_v1") {
    throw new Error(`unsupported schema: ${String(payload.schema)}`);
  }

  return {
    schema: "cp_graph_mem_v1",
    vertices: payload.vertices.map((v) => ({
      id: v.id,
      point: pointEFromJson(v.point, `vertices[${v.id}].point`),
      pointApprox: {
        x: v.point.x_approx,
        y: v.point.y_approx,
      },
      isCorner: v.is_corner,
      isBoundary: v.is_boundary,
    })),
    edges: payload.edges.map((e) => ({
      id: e.id,
      v0: e.v0,
      v1: e.v1,
      isBoundary: e.is_boundary,
      axis8: e.axis8,
      birthOrder: e.birth_order,
    })),
    corners: [...payload.corners],
    stats: {
      vertexCount: payload.stats.vertex_count,
      edgeCount: payload.stats.edge_count,
      boundaryEdgeCount: payload.stats.boundary_edge_count,
      cornerCount: payload.stats.corner_count,
    },
    params: payload.params ?? undefined,
    searchStats: payload.search_stats ?? undefined,
    stageLogs: payload.stage_logs ?? undefined,
  };
}

export function memGraphToCpGraphV1(
  graph: CreaseGraphMem,
  opts?: {
    domain?: CpGraphV1Json["domain"];
    direction?: CpGraphV1Json["direction"];
    params?: Record<string, unknown> | null;
    searchStats?: Record<string, number> | null;
    stageLogs?: Array<Record<string, unknown>> | null;
  },
): CpGraphV1Json {
  if (graph.schema !== "cp_graph_mem_v1") {
    throw new Error(`unsupported mem schema: ${String(graph.schema)}`);
  }

  return {
    schema: "cp_graph_v1",
    domain: opts?.domain ?? DEFAULT_DOMAIN,
    direction: opts?.direction ?? DEFAULT_DIRECTION,
    vertices: graph.vertices.map((v) => ({
      id: v.id,
      point: {
        ...pointEToJson(v.point, `vertices[${v.id}].point`),
        x_approx: v.pointApprox.x,
        y_approx: v.pointApprox.y,
      },
      is_corner: v.isCorner,
      is_boundary: v.isBoundary,
    })),
    edges: graph.edges.map((e) => ({
      id: e.id,
      v0: e.v0,
      v1: e.v1,
      is_boundary: e.isBoundary,
      axis8: e.axis8,
      birth_order: e.birthOrder,
    })),
    corners: [...graph.corners],
    stats: {
      vertex_count: graph.stats.vertexCount,
      edge_count: graph.stats.edgeCount,
      boundary_edge_count: graph.stats.boundaryEdgeCount,
      corner_count: graph.stats.cornerCount,
    },
    params: opts?.params ?? graph.params ?? null,
    search_stats: opts?.searchStats ?? graph.searchStats ?? null,
    stage_logs: opts?.stageLogs ?? graph.stageLogs ?? null,
  };
}

export function vec2(x: number, y: number): Vec2 {
  return { x, y };
}
