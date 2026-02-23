import { HALF, ZERO } from "./qsqrt2";
import { enumerateGridPoints, GridCreaseGraph } from "./creasegen_graph";
import { pointKey } from "./creasegen_grid_utils";
import type { PointE } from "./types";

function assertCondition(cond: boolean, message: string): void {
  if (!cond) {
    throw new Error(message);
  }
}

function pointAt(x: PointE["x"], y: PointE["y"]): PointE {
  return { x, y };
}

export function runCreasegenGraphFixture(): void {
  const { points, p2i } = enumerateGridPoints(1, 1, 1);
  assertCondition(points.length > 0, "enumerateGridPoints should generate points");

  const g = new GridCreaseGraph({
    points,
    p2i,
    useLocalRayDirty: false,
  });

  g.initSquareBoundary();
  assertCondition(g.edges.size === 4, "square boundary should have 4 edges");
  assertCondition(g.boundaryEdges.size === 4, "square boundary should mark all edges as boundary");
  assertCondition(g.activeVertices.size === 4, "square boundary should activate 4 vertices");

  const center = pointAt(ZERO, ZERO);
  const centerV = g.addVertex(center);
  const shot = g.shootRayAndSplit(centerV, 0);
  assertCondition(shot !== null, "center ray should hit right boundary");

  assertCondition(g.edges.size === 6, "split + new segment should produce 6 total edges");
  assertCondition(g.boundaryEdges.size === 5, "boundary edge should split into two boundary edges");
  assertCondition(g.activeVertices.size === 6, "center and split point should be activated");

  const splitPoint = pointAt(HALF, ZERO);
  const splitV = p2i.get(pointKey(splitPoint));
  assertCondition(splitV !== undefined, "split point must exist in pre-enumerated grid");
  if (splitV === undefined) {
    throw new Error("split point index should be resolved");
  }
  assertCondition(g.activeVertices.has(splitV), "split point should be active after ray split");

  const eastHit = g.rayNextAt(centerV, 0);
  assertCondition(eastHit !== null, "ray cache should provide east hit from center");
}
