import { runCreasegen } from "./creasegen";
import { fromDyadic, fromInt } from "./qsqrt2";
import type { PointE } from "./types";

function assertCondition(cond: boolean, message: string): void {
  if (!cond) {
    throw new Error(message);
  }
}

function point(x: PointE["x"], y: PointE["y"]): PointE {
  return { x, y };
}

function findVertexIdByPoint(
  graph: ReturnType<typeof runCreasegen>["graph"],
  p: PointE,
): number | undefined {
  const found = graph.vertices.find(
    (v) =>
      v.point.x.a === p.x.a &&
      v.point.x.b === p.x.b &&
      v.point.x.k === p.x.k &&
      v.point.y.a === p.y.a &&
      v.point.y.b === p.y.b &&
      v.point.y.k === p.y.k,
  );
  return found?.id;
}

export function runCreasegenFixture(): void {
  const zero = fromInt(0);
  const one = fromInt(1);
  const half = fromDyadic(1, 1);
  const corners: PointE[] = [
    point(zero, zero),
    point(zero, one),
    point(one, zero),
    point(one, one),
    point(half, half),
  ];

  const result = runCreasegen({
    corners,
    config: {
      aMax: 1,
      bMax: 1,
      kMax: 1,
      enforceSymmetry: true,
      maxDepth: 1,
      branchPerNode: 2,
      maxNodes: 64,
    },
  });

  assertCondition(result.graph.stats.cornerCount === corners.length, "corner count mismatch");
  assertCondition(result.graph.stats.boundaryEdgeCount === 4, "boundary edge count should remain 4");
  assertCondition(result.graph.stats.edgeCount >= 5, "expected interior edges after seeding");

  const centerId = findVertexIdByPoint(result.graph, point(half, half));
  assertCondition(centerId !== undefined, "center corner should exist in graph");
  if (centerId === undefined) {
    throw new Error("center id missing");
  }
  const centerVertex = result.graph.vertices.find((v) => v.id === centerId);
  assertCondition(Boolean(centerVertex?.isCorner), "center should be marked as corner");

  assertCondition(
    Number.isInteger(result.metrics.cornerViolationsAfter) &&
      result.metrics.cornerViolationsAfter >= 0,
    "cornerViolationsAfter should be a non-negative integer",
  );
  assertCondition(
    Number.isInteger(result.metrics.kawasakiViolationsAfter) &&
      result.metrics.kawasakiViolationsAfter >= 0,
    "kawasakiViolationsAfter should be a non-negative integer",
  );
  assertCondition(
    Number.isInteger(result.metrics.priorityCornerKawasakiViolationsAfter) &&
      result.metrics.priorityCornerKawasakiViolationsAfter >= 0,
    "priorityCornerKawasakiViolationsAfter should be a non-negative integer",
  );
  assertCondition(
    result.metrics.priorityCornerKawasakiViolationsAfter <=
      result.metrics.kawasakiViolationsAfter,
    "priority corner violations should be <= global kawasaki violations",
  );

  assertCondition(
    typeof result.graph.searchStats === "object" && result.graph.searchStats !== undefined,
    "searchStats should be present after seeded + greedy run",
  );
  assertCondition(
    (result.graph.searchStats?.greedy_depth_round ?? 0) >= 1,
    "greedy_depth_round should be recorded",
  );
  assertCondition(
    (result.graph.searchStats?.recurse_calls ?? 0) >= 1,
    "recurse_calls should be recorded by dfs repair",
  );
  assertCondition(
    (result.graph.stageLogs?.length ?? 0) >= 1,
    "stageLogs should include at least one stage entry",
  );

  const staged = runCreasegen({
    corners,
    config: {
      aMax: 1,
      bMax: 1,
      kMax: 2,
      kStart: 1,
      stagedKRelax: true,
      enforceSymmetry: true,
      maxDepth: 2,
      branchPerNode: 2,
      maxNodes: 64,
    },
  });
  assertCondition(
    (staged.graph.stageLogs?.length ?? 0) >= 2,
    "stagedKRelax should record multiple stage logs when kStart < kMax",
  );
  assertCondition(
    Number(staged.graph.params?.kStartEffective ?? -1) === 1,
    "params.kStartEffective should reflect staged start k",
  );
  assertCondition(
    Number(staged.graph.params?.kEffective ?? -1) === 2,
    "params.kEffective should reflect final stage k",
  );

  const cornersFine: PointE[] = [
    point(zero, zero),
    point(zero, one),
    point(one, zero),
    point(one, one),
    point(fromDyadic(1, 3), fromDyadic(5, 3)),
  ];
  const stagedFine = runCreasegen({
    corners: cornersFine,
    config: {
      aMax: 1,
      bMax: 1,
      kMax: 3,
      kStart: 1,
      stagedKRelax: true,
      enforceSymmetry: false,
      maxDepth: 1,
      branchPerNode: 1,
      maxNodes: 24,
      autoExpandGrid: false,
      seedAutoExpand: false,
      finalPrune: false,
    },
  });
  assertCondition(
    Number(stagedFine.graph.params?.kStartEffective ?? -1) >= 3,
    "kStartEffective must be raised to include input corner resolution",
  );

  const guided = runCreasegen({
    corners,
    config: {
      aMax: 1,
      bMax: 1,
      kMax: 1,
      enforceSymmetry: true,
      maxDepth: 2,
      branchPerNode: 2,
      maxNodes: 80,
      autoExpandGrid: false,
      finalPrune: false,
      seedAutoExpand: false,
      draftGuided: true,
      draftMaxDepth: 1,
      draftBranchPerNode: 1,
      draftMaxNodes: 40,
    },
  });
  const guidedLogs = guided.graph.stageLogs ?? [];
  assertCondition(
    guidedLogs.some((l) => l.type === "draft_guided"),
    "draftGuided run should record draft_guided stage log",
  );
  assertCondition(
    typeof guided.graph.searchStats?.draft_hint_corner_count === "number",
    "draftGuided run should record draft hint corner count",
  );
}
