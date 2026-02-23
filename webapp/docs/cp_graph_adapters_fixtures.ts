import type { CpGraphV1Json } from "./engine_types";
import { cpGraphV1ToMemGraph, memGraphToCpGraphV1 } from "./cp_graph_adapters";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function edgeKey(v0: number, v1: number): string {
  return v0 < v1 ? `${v0}-${v1}` : `${v1}-${v0}`;
}

function collectEdgeKeys(payload: CpGraphV1Json): string[] {
  return payload.edges
    .map((e) => edgeKey(e.v0, e.v1))
    .sort();
}

export const CP_GRAPH_FIXTURE_SQUARE: CpGraphV1Json = {
  schema: "cp_graph_v1",
  domain: {
    shape: "unit_square",
    x_min: 0,
    x_max: 1,
    y_min: 0,
    y_max: 1,
  },
  direction: {
    dir_count: 16,
    axis_count: 8,
  },
  vertices: [
    {
      id: 0,
      point: {
        x: { a: 0, b: 0, k: 0 },
        y: { a: 0, b: 0, k: 0 },
        x_approx: 0,
        y_approx: 0,
      },
      is_corner: true,
      is_boundary: true,
    },
    {
      id: 1,
      point: {
        x: { a: 1, b: 0, k: 0 },
        y: { a: 0, b: 0, k: 0 },
        x_approx: 1,
        y_approx: 0,
      },
      is_corner: true,
      is_boundary: true,
    },
    {
      id: 2,
      point: {
        x: { a: 1, b: 0, k: 0 },
        y: { a: 1, b: 0, k: 0 },
        x_approx: 1,
        y_approx: 1,
      },
      is_corner: true,
      is_boundary: true,
    },
    {
      id: 3,
      point: {
        x: { a: 0, b: 0, k: 0 },
        y: { a: 1, b: 0, k: 0 },
        x_approx: 0,
        y_approx: 1,
      },
      is_corner: true,
      is_boundary: true,
    },
  ],
  edges: [
    { id: 0, v0: 0, v1: 1, is_boundary: true, axis8: 0, birth_order: 0 },
    { id: 1, v0: 1, v1: 2, is_boundary: true, axis8: 2, birth_order: 1 },
    { id: 2, v0: 2, v1: 3, is_boundary: true, axis8: 0, birth_order: 2 },
    { id: 3, v0: 3, v1: 0, is_boundary: true, axis8: 2, birth_order: 3 },
  ],
  corners: [0, 1, 2, 3],
  stats: {
    vertex_count: 4,
    edge_count: 4,
    boundary_edge_count: 4,
    corner_count: 4,
  },
  params: { fixture: true },
  search_stats: { recurse_calls: 0 },
  stage_logs: [{ type: "fixture" }],
};

export function runCpGraphAdaptersRoundtripFixture(): void {
  const mem = cpGraphV1ToMemGraph(CP_GRAPH_FIXTURE_SQUARE);
  const back = memGraphToCpGraphV1(mem);

  assert(back.schema === "cp_graph_v1", "schema mismatch");
  assert(back.vertices.length === CP_GRAPH_FIXTURE_SQUARE.vertices.length, "vertex count mismatch");
  assert(back.edges.length === CP_GRAPH_FIXTURE_SQUARE.edges.length, "edge count mismatch");
  assert(
    JSON.stringify(back.corners) === JSON.stringify(CP_GRAPH_FIXTURE_SQUARE.corners),
    "corner ids mismatch",
  );

  const lhsEdges = collectEdgeKeys(CP_GRAPH_FIXTURE_SQUARE);
  const rhsEdges = collectEdgeKeys(back);
  assert(JSON.stringify(lhsEdges) === JSON.stringify(rhsEdges), "edge topology mismatch");

  assert(back.stats.vertex_count === 4, "stats.vertex_count mismatch");
  assert(back.stats.edge_count === 4, "stats.edge_count mismatch");
  assert(back.stats.boundary_edge_count === 4, "stats.boundary_edge_count mismatch");
  assert(back.stats.corner_count === 4, "stats.corner_count mismatch");
}
