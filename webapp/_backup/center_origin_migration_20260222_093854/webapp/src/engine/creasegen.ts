import { resolveRunConfig } from "./defaults";
import { nearestDirIdx } from "./creasegen_direction";
import {
  admissibleDirsForVertex,
  cornerConditionErrorWithAddedDir,
  detectExpandNeed,
  effectiveStallRounds,
  expandMode,
  expandRequestFromStats,
  mergeSearchStats,
  planExpandTarget,
  usedDirIndices,
} from "./creasegen_expand";
import { applyRayAction } from "./creasegen_actions";
import {
  globalScore,
  kawasakiScore,
  priorityCornerKawasakiScore,
} from "./creasegen_evaluation";
import { type GridCreaseGraph } from "./creasegen_graph";
import {
  cloneGraph,
  graphStats,
  makeGridGraph,
  remapGraphToNewGrid,
} from "./creasegen_graph_ops";
import { applyFinalPruneRounds } from "./creasegen_final_prune";
import { cornersDiagSymmetric } from "./creasegen_predicates";
import { cornerConditionError, cornerLineCount, requiredCornerLines } from "./creasegen_scoring";
import {
  runDfsRepair,
  runGreedyRepair,
  type PreferredDirHints,
} from "./creasegen_search";
import { pointKey, requiredGridBoundsForPoint } from "./creasegen_grid_utils";
import { addSegmentWithSplitsIds, seedDirectCornerConnections } from "./creasegen_seeding";
import { pointEApprox } from "./qsqrt2";
import type { CreaseBuildInput, CreaseGraphMem, CreaseRunResult, RunConfig } from "./types";

const MAX_WORK_BOUND = 12;

function compareNumericTuple(a: readonly number[], b: readonly number[]): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    if (a[i] < b[i]) {
      return -1;
    }
    if (a[i] > b[i]) {
      return 1;
    }
  }
  if (a.length < b.length) {
    return -1;
  }
  if (a.length > b.length) {
    return 1;
  }
  return 0;
}

function resolveEffectiveBounds(
  corners: ReadonlyArray<CreaseBuildInput["corners"][number]>,
  config: RunConfig,
  requiredPoints?: ReadonlyArray<CreaseBuildInput["corners"][number]>,
): { aMax: number; bMax: number; kMax: number } {
  let aMax = config.aMax;
  let bMax = config.bMax;
  let kMax = config.kMax;
  const allPoints = requiredPoints ? [...corners, ...requiredPoints] : [...corners];
  for (const p of allPoints) {
    const req = requiredGridBoundsForPoint(p);
    if (req === null) {
      throw new Error("point has unsupported exact coordinate bounds");
    }
    aMax = Math.max(aMax, req.aMax);
    bMax = Math.max(bMax, req.bMax);
    kMax = Math.max(kMax, req.kMax);
  }
  return { aMax, bMax, kMax };
}

function resolveRequiredPointBounds(
  points: ReadonlyArray<CreaseBuildInput["corners"][number]>,
): { aMax: number; bMax: number; kMax: number } {
  let aMax = 0;
  let bMax = 0;
  let kMax = 0;
  for (const p of points) {
    const req = requiredGridBoundsForPoint(p);
    if (req === null) {
      throw new Error("point has unsupported exact coordinate bounds");
    }
    aMax = Math.max(aMax, req.aMax);
    bMax = Math.max(bMax, req.bMax);
    kMax = Math.max(kMax, req.kMax);
  }
  return { aMax, bMax, kMax };
}

function axis8FromEdge(g: GridCreaseGraph, i: number, j: number): number {
  const bucket = g.edgeDirBucketAt(i, j);
  if (bucket !== null && bucket !== undefined) {
    return bucket;
  }
  const [x1, y1] = g.pointsF[i];
  const [x2, y2] = g.pointsF[j];
  return nearestDirIdx(x2 - x1, y2 - y1) % 8;
}

function buildMemGraphFromGrid(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  config: RunConfig,
  finalBudget: {
    aWork: number;
    bWork: number;
    aNormWork: number;
    bNormWork: number;
  },
  searchStats: Record<string, number>,
  stageLogs: Array<Record<string, unknown>>,
  kStartEffective: number,
  effectiveK: number,
  seedExpandRounds: number,
): CreaseGraphMem {
  const activeVertices = [...g.activeVertices].sort((a, b) => a - b);
  const cornerSet = new Set(cornerIds);
  const boundaryVertexSet = new Set<number>();
  for (const [i, j] of g.boundaryEdgePairs()) {
    boundaryVertexSet.add(i);
    boundaryVertexSet.add(j);
  }

  const vertices = activeVertices.map((v) => {
    const [x, y] = pointEApprox(g.points[v]);
    return {
      id: v,
      point: g.points[v],
      pointApprox: { x, y },
      isCorner: cornerSet.has(v),
      isBoundary: boundaryVertexSet.has(v),
    };
  });

  const sortedEdges = g
    .edgePairs()
    .map(([i, j]) => {
      const birth = g.edgeBirthOrder(i, j);
      if (birth === undefined) {
        throw new Error(`edge birth order missing: ${i},${j}`);
      }
      return { i, j, birth };
    })
    .sort((lhs, rhs) => {
      if (lhs.birth !== rhs.birth) {
        return lhs.birth - rhs.birth;
      }
      if (lhs.i !== rhs.i) {
        return lhs.i - rhs.i;
      }
      return lhs.j - rhs.j;
    });

  const edges = sortedEdges.map((e, edgeId) => ({
    id: edgeId,
    v0: e.i,
    v1: e.j,
    isBoundary: g.isBoundaryEdge(e.i, e.j),
    axis8: axis8FromEdge(g, e.i, e.j),
    birthOrder: e.birth,
  }));

  const params: Record<string, unknown> = {
    ...config,
    aMaxEffective: finalBudget.aWork,
    bMaxEffective: finalBudget.bWork,
    aNormEffective: finalBudget.aNormWork,
    bNormEffective: finalBudget.bNormWork,
    kMaxEffective: effectiveK,
    kStartEffective,
    kEffective: effectiveK,
    seedExpandRoundsUsed: seedExpandRounds,
  };

  return {
    schema: "cp_graph_mem_v1",
    vertices,
    edges,
    corners: [...new Set(cornerIds)].sort((a, b) => a - b),
    stats: {
      vertexCount: vertices.length,
      edgeCount: edges.length,
      boundaryEdgeCount: edges.filter((e) => e.isBoundary).length,
      cornerCount: cornerSet.size,
    },
    params,
    searchStats: Object.keys(searchStats).length > 0 ? searchStats : undefined,
    stageLogs: stageLogs.length > 0 ? stageLogs : undefined,
  };
}

function extractPreferredDirHintsFromDraft(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  config: RunConfig,
): PreferredDirHints {
  const out: PreferredDirHints = {};
  const tol = 1e-12;
  for (const v of cornerIds) {
    if (!g.activeVertices.has(v)) {
      continue;
    }
    const beforeErr = cornerConditionError(g, v, config.cornerMaxDeg);
    const needLines = requiredCornerLines(g, v, {
      maxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
    });
    const curLines = cornerLineCount(g, v);
    const deficit = Math.max(0, needLines - curLines);
    if (deficit <= 0 && beforeErr <= tol) {
      continue;
    }

    const used = usedDirIndices(g, v, false);
    const row = g.ensureRayNext(v);
    const cand: Array<[number, number]> = [];
    for (const d of admissibleDirsForVertex(g, v, config.enforceSymmetry)) {
      if (used.has(d)) {
        continue;
      }
      if (row[d] === null) {
        continue;
      }
      const afterErr = cornerConditionErrorWithAddedDir(g, v, d, config.cornerMaxDeg);
      const errGain = beforeErr - afterErr;
      cand.push([errGain, d]);
    }
    if (cand.length === 0) {
      continue;
    }

    cand.sort((lhs, rhs) => {
      if (lhs[0] !== rhs[0]) {
        return rhs[0] - lhs[0];
      }
      return lhs[1] - rhs[1];
    });
    const needDirs = Math.min(cand.length, Math.max(1, deficit));
    const selected = cand.slice(0, needDirs).map((c) => c[1]);
    if (selected.length > 0) {
      out[pointKey(g.points[v])] = selected;
    }
  }
  return out;
}

function applyPreferredHintsAtSearchStart(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  hints: PreferredDirHints | null,
  config: RunConfig,
  stats: Record<string, number>,
): {
  graph: GridCreaseGraph;
  attempted: number;
  applied: number;
  failed: number;
  alreadyUsed: number;
  missingCorner: number;
} {
  if (!hints || Object.keys(hints).length === 0) {
    return {
      graph: g,
      attempted: 0,
      applied: 0,
      failed: 0,
      alreadyUsed: 0,
      missingCorner: 0,
    };
  }

  let h = g;
  let attempted = 0;
  let applied = 0;
  let failed = 0;
  let alreadyUsed = 0;
  let missingCorner = 0;

  const cornerKeySet = new Set<string>();
  for (const v of cornerIds) {
    if (!h.activeVertices.has(v)) {
      continue;
    }
    cornerKeySet.add(pointKey(h.points[v]));
  }

  for (const [key, dirs] of Object.entries(hints)) {
    if (!cornerKeySet.has(key)) {
      missingCorner += dirs.length;
      continue;
    }
    const v = h.pointToId.get(key);
    if (v === undefined || !h.activeVertices.has(v)) {
      missingCorner += dirs.length;
      continue;
    }
    for (const d of dirs) {
      attempted += 1;
      if (usedDirIndices(h, v, false).has(d)) {
        alreadyUsed += 1;
        continue;
      }
      const nh = applyRayAction(h, {
        vIdx: v,
        dirIdx: d,
        enforceSymmetry: config.enforceSymmetry,
        stats,
      });
      if (nh === null) {
        failed += 1;
        continue;
      }
      h = nh;
      applied += 1;
    }
  }

  return {
    graph: h,
    attempted,
    applied,
    failed,
    alreadyUsed,
    missingCorner,
  };
}

export function runCreasegen(input: CreaseBuildInput): CreaseRunResult {
  const t0 = Date.now();
  const config = resolveRunConfig(input.config);
  const corners = input.corners;
  if (corners.length < 3) {
    throw new Error("corners must have at least 3 points");
  }
  if (config.enforceSymmetry && !cornersDiagSymmetric(corners)) {
    throw new Error("enforceSymmetry=true requires corners to be y=x symmetric");
  }

  const initialCornerEdgePairs: Array<{ cornerI: number; cornerJ: number }> = [];
  if (input.seedEdges) {
    const seen = new Set<string>();
    for (const e of input.seedEdges) {
      const i = e.cornerI;
      const j = e.cornerJ;
      if (!Number.isInteger(i) || !Number.isInteger(j)) {
        continue;
      }
      if (i < 0 || j < 0 || i >= corners.length || j >= corners.length || i === j) {
        continue;
      }
      const a = i < j ? i : j;
      const b = i < j ? j : i;
      const key = `${a},${b}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      initialCornerEdgePairs.push({ cornerI: a, cornerJ: b });
    }
  }
  const initialSeedSegments: Array<{
    from: CreaseBuildInput["corners"][number];
    to: CreaseBuildInput["corners"][number];
  }> = [];
  if (input.seedSegments) {
    const seen = new Set<string>();
    for (const seg of input.seedSegments) {
      if (!seg?.from || !seg?.to) {
        continue;
      }
      const fromKey = pointKey(seg.from);
      const toKey = pointKey(seg.to);
      if (fromKey === toKey) {
        continue;
      }
      const key = fromKey < toKey ? `${fromKey}|${toKey}` : `${toKey}|${fromKey}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      initialSeedSegments.push({ from: seg.from, to: seg.to });
    }
  }
  const requiredPointsForSeedSegments: Array<CreaseBuildInput["corners"][number]> = [];
  for (const seg of initialSeedSegments) {
    requiredPointsForSeedSegments.push(seg.from, seg.to);
  }
  const requiredInputBounds = resolveRequiredPointBounds([
    ...corners,
    ...requiredPointsForSeedSegments,
  ]);

  const effectiveBounds = resolveEffectiveBounds(corners, config, requiredPointsForSeedSegments);
  const searchStats: Record<string, number> = {};
  const stageLogs: Array<Record<string, unknown>> = [];

  const stagedBaseK = Math.max(1, Math.min(config.kStart, effectiveBounds.kMax));
  let kStartEffective = config.stagedKRelax
    ? Math.max(requiredInputBounds.kMax, stagedBaseK)
    : effectiveBounds.kMax;
  let effectiveK = kStartEffective;
  let aWork = effectiveBounds.aMax;
  let bWork = effectiveBounds.bMax;
  let aNormWork = 0;
  let bNormWork = 0;
  let seeded: { graph: GridCreaseGraph; cornerIds: number[] } | null = null;

  let seedExpandRounds = 0;
  while (true) {
    const seedRoundStats: Record<string, number> = {};
    seeded = makeGridGraph({
      corners,
      initialCornerEdgePairs,
      initialSegments: initialSeedSegments,
      aMax: aWork,
      bMax: bWork,
      kMax: kStartEffective,
      cornerMaxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
      enforceSymmetry: config.enforceSymmetry,
      useLocalRayDirty: config.useLocalRayDirty,
      seedStats: seedRoundStats,
      seedDirectCornerConnections,
      addSegmentWithSplitsIds,
    });
    mergeSearchStats(searchStats, seedRoundStats);
    if (!config.seedAutoExpand) {
      break;
    }
    const req = expandRequestFromStats(seedRoundStats);
    if (req === null) {
      break;
    }
    if (seedExpandRounds >= Math.max(0, config.seedAutoExpandMaxRounds)) {
      searchStats.seed_auto_expand_round_limit = (searchStats.seed_auto_expand_round_limit ?? 0) + 1;
      break;
    }

    const targetK = config.stagedKRelax ? kStartEffective : Math.max(kStartEffective, req.needK);
    const targetANorm = Math.max(aNormWork, req.needANorm);
    const targetBNorm = Math.max(bNormWork, req.needBNorm);
    let targetA = Math.max(aWork, req.needA, targetANorm << targetK);
    let targetB = Math.max(bWork, req.needB, targetBNorm << targetK);
    if (targetA > MAX_WORK_BOUND) {
      targetA = MAX_WORK_BOUND;
      searchStats.seed_auto_expand_clamped_bound =
        (searchStats.seed_auto_expand_clamped_bound ?? 0) + 1;
    }
    if (targetB > MAX_WORK_BOUND) {
      targetB = MAX_WORK_BOUND;
      searchStats.seed_auto_expand_clamped_bound =
        (searchStats.seed_auto_expand_clamped_bound ?? 0) + 1;
    }
    if (
      targetA <= aWork &&
      targetB <= bWork &&
      targetK <= kStartEffective &&
      targetANorm <= aNormWork &&
      targetBNorm <= bNormWork
    ) {
      break;
    }

    seedExpandRounds += 1;
    searchStats.seed_auto_expand_trigger = (searchStats.seed_auto_expand_trigger ?? 0) + 1;
    aWork = targetA;
    bWork = targetB;
    aNormWork = targetANorm;
    bNormWork = targetBNorm;
    kStartEffective = targetK;
    stageLogs.push({
      type: "seed_auto_expand",
      round: seedExpandRounds,
      a_max: aWork,
      b_max: bWork,
      a_norm: aNormWork,
      b_norm: bNormWork,
      k_max: kStartEffective,
      seed_stats: seedRoundStats,
    });
  }

  if (seeded === null) {
    throw new Error("seed stage failed to initialize graph");
  }

  let curGraph = seeded.graph;
  let curCornerIds = seeded.cornerIds;
  let preferredDirHints: PreferredDirHints | null = null;

  if (config.draftGuided) {
    const draftConfig: RunConfig = {
      ...config,
      maxDepth: Math.max(0, Math.min(config.maxDepth, config.draftMaxDepth)),
      branchPerNode: Math.max(1, Math.min(config.branchPerNode, config.draftBranchPerNode)),
      maxNodes: Math.max(1, Math.min(config.maxNodes, config.draftMaxNodes)),
      autoExpandGrid: false,
      finalPrune: false,
      seedAutoExpand: false,
      draftGuided: false,
    };
    const draftStats: Record<string, number> = {};
    const draftBefore = graphStats(curGraph);
    const draftBase = cloneGraph(curGraph);
    const draftGreedy = runGreedyRepair(
      draftBase,
      curCornerIds,
      draftConfig,
      draftStats,
    );
    const draftBest = runDfsRepair(
      draftGreedy,
      curCornerIds,
      draftConfig,
      draftStats,
      null,
    );
    preferredDirHints = extractPreferredDirHintsFromDraft(draftBest, curCornerIds, config);
    const hintCornerCount = Object.keys(preferredDirHints).length;
    const hintDirTotal = Object.values(preferredDirHints).reduce((acc, ds) => acc + ds.length, 0);
    searchStats.draft_hint_corner_count = hintCornerCount;
    searchStats.draft_hint_dir_total = hintDirTotal;

    stageLogs.push({
      type: "draft_guided",
      hint_corner_count: hintCornerCount,
      hint_dir_total: hintDirTotal,
      draft_params: {
        max_depth: draftConfig.maxDepth,
        branch_per_node: draftConfig.branchPerNode,
        max_nodes: draftConfig.maxNodes,
        auto_expand_grid: draftConfig.autoExpandGrid,
        seed_auto_expand: draftConfig.seedAutoExpand,
      },
      draft_stats_before: draftBefore,
      draft_stats_after: graphStats(draftBest),
    });

    const forced = applyPreferredHintsAtSearchStart(
      curGraph,
      curCornerIds,
      preferredDirHints,
      config,
      searchStats,
    );
    let forcedGraph = forced.graph;
    let forcedReverted = false;
    const beforeForceScore = globalScore(curGraph, curCornerIds, {
      maxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
      kawasakiTol: config.kawasakiTol,
    });
    const afterForceScore = globalScore(forcedGraph, curCornerIds, {
      maxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
      kawasakiTol: config.kawasakiTol,
    });
    const beforeForceCk = priorityCornerKawasakiScore(curGraph, curCornerIds, {
      tol: config.kawasakiTol,
    });
    const afterForceCk = priorityCornerKawasakiScore(forcedGraph, curCornerIds, {
      tol: config.kawasakiTol,
    });
    const scoreNonworse = compareNumericTuple(afterForceScore, beforeForceScore) <= 0;
    const ckNonworse =
      afterForceCk[0] < beforeForceCk[0] ||
      (afterForceCk[0] === beforeForceCk[0] && afterForceCk[1] <= beforeForceCk[1] + 1e-12);
    if (!scoreNonworse || !ckNonworse) {
      forcedGraph = curGraph;
      forcedReverted = true;
      searchStats.draft_hint_forced_reverted_worse =
        (searchStats.draft_hint_forced_reverted_worse ?? 0) + 1;
    }
    curGraph = forcedGraph;
    searchStats.draft_hint_forced_attempt = forced.attempted;
    searchStats.draft_hint_forced_applied = forced.applied;
    searchStats.draft_hint_forced_failed = forced.failed;
    searchStats.draft_hint_forced_already_used = forced.alreadyUsed;
    searchStats.draft_hint_forced_missing_corner = forced.missingCorner;
    stageLogs.push({
      type: "draft_hint_force_start",
      attempted: forced.attempted,
      applied: forced.applied,
      failed: forced.failed,
      already_used: forced.alreadyUsed,
      missing_corner: forced.missingCorner,
      reverted_worse: forcedReverted,
      score_before: beforeForceScore,
      score_after: afterForceScore,
      stats_after: graphStats(curGraph),
    });
  }

  const kEnd = config.stagedKRelax ? effectiveBounds.kMax : kStartEffective;

  for (let kCur = kStartEffective; kCur <= kEnd; kCur += 1) {
    let autoExpandRounds = 0;
    let stallStreak = 0;
    if (kCur > kStartEffective) {
      aWork = Math.max(aWork, aNormWork << kCur);
      bWork = Math.max(bWork, bNormWork << kCur);
      if (aWork > MAX_WORK_BOUND) {
        aWork = MAX_WORK_BOUND;
        searchStats.stage_remap_clamped_bound = (searchStats.stage_remap_clamped_bound ?? 0) + 1;
      }
      if (bWork > MAX_WORK_BOUND) {
        bWork = MAX_WORK_BOUND;
        searchStats.stage_remap_clamped_bound = (searchStats.stage_remap_clamped_bound ?? 0) + 1;
      }
      const expanded = makeGridGraph({
        corners,
        initialCornerEdgePairs,
        initialSegments: initialSeedSegments,
        aMax: aWork,
        bMax: bWork,
        kMax: kCur,
        cornerMaxDeg: config.cornerMaxDeg,
        minCornerLines: config.minCornerLines,
        enforceSymmetry: config.enforceSymmetry,
        useLocalRayDirty: config.useLocalRayDirty,
        seedStats: undefined,
        seedDirectCornerConnections,
        addSegmentWithSplitsIds,
      });
      remapGraphToNewGrid(curGraph, expanded.graph);
      curGraph = expanded.graph;
      curCornerIds = expanded.cornerIds;
      searchStats.stage_remap_round = (searchStats.stage_remap_round ?? 0) + 1;
    }

    let kLocal = kCur;
    const maxStageIters = Math.max(1, (config.autoExpandMaxRounds + 1) * 12);
    let stageIter = 0;
    while (true) {
      stageIter += 1;
      if (stageIter > maxStageIters) {
        searchStats.stage_iter_limit = (searchStats.stage_iter_limit ?? 0) + 1;
        break;
      }
      const baseScore = globalScore(curGraph, curCornerIds, {
        maxDeg: config.cornerMaxDeg,
        minCornerLines: config.minCornerLines,
        kawasakiTol: config.kawasakiTol,
      });
      const roundStats: Record<string, number> = {};
      const repairedGreedy = runGreedyRepair(
        curGraph,
        curCornerIds,
        config,
        roundStats,
      );
      const repaired = runDfsRepair(
        repairedGreedy,
        curCornerIds,
        config,
        roundStats,
        preferredDirHints,
      );
      mergeSearchStats(searchStats, roundStats);
      const bestScoreLocal = globalScore(repaired, curCornerIds, {
        maxDeg: config.cornerMaxDeg,
        minCornerLines: config.minCornerLines,
        kawasakiTol: config.kawasakiTol,
      });
      curGraph = repaired;

      let improved = false;
      for (let i = 0; i < baseScore.length; i += 1) {
        if (bestScoreLocal[i] < baseScore[i]) {
          improved = true;
          break;
        }
        if (bestScoreLocal[i] > baseScore[i]) {
          break;
        }
      }
      if (!config.autoExpandGrid) {
        break;
      }
      if (improved) {
        stallStreak = 0;
        searchStats.coarse_round_improved = (searchStats.coarse_round_improved ?? 0) + 1;
        if (bestScoreLocal[0] === 0 && bestScoreLocal[1] === 0 && bestScoreLocal[2] === 0) {
          break;
        }
        continue;
      }

      stallStreak += 1;
      searchStats.coarse_round_stalled = (searchStats.coarse_round_stalled ?? 0) + 1;
      const stallNeed = effectiveStallRounds({
        activeVertices: curGraph.activeVertices.size,
        baseRounds: config.expandStallRounds,
        maxNodes: config.maxNodes,
      });
      searchStats.stall_round_need_max = Math.max(searchStats.stall_round_need_max ?? 0, stallNeed);
      if (stallStreak < stallNeed) {
        continue;
      }

      const need = detectExpandNeed(curGraph, {
        cornerIds: curCornerIds,
        roundStats,
        cornerMaxDeg: config.cornerMaxDeg,
        minCornerLines: config.minCornerLines,
        enforceSymmetry: config.enforceSymmetry,
        searchStats,
      });
      if (need === null) {
        break;
      }
      let target = planExpandTarget(need, {
        aWork,
        bWork,
        kLocal,
        aNormWork,
        bNormWork,
        stagedKRelax: config.stagedKRelax,
      });
      if (target === null) {
        break;
      }
      if (autoExpandRounds >= Math.max(0, config.autoExpandMaxRounds)) {
        searchStats.auto_expand_round_limit = (searchStats.auto_expand_round_limit ?? 0) + 1;
        break;
      }

      if (target.targetA > MAX_WORK_BOUND) {
        target = { ...target, targetA: MAX_WORK_BOUND };
        searchStats.auto_expand_clamped_bound = (searchStats.auto_expand_clamped_bound ?? 0) + 1;
      }
      if (target.targetB > MAX_WORK_BOUND) {
        target = { ...target, targetB: MAX_WORK_BOUND };
        searchStats.auto_expand_clamped_bound = (searchStats.auto_expand_clamped_bound ?? 0) + 1;
      }
      if (
        target.targetA <= aWork &&
        target.targetB <= bWork &&
        target.targetK <= kLocal &&
        target.targetANorm <= aNormWork &&
        target.targetBNorm <= bNormWork
      ) {
        searchStats.auto_expand_nochange = (searchStats.auto_expand_nochange ?? 0) + 1;
        break;
      }

      const mode = expandMode(target, {
        curA: aWork,
        curB: bWork,
        curK: kLocal,
        curANorm: aNormWork,
        curBNorm: bNormWork,
      });

      autoExpandRounds += 1;
      searchStats.auto_expand_trigger = (searchStats.auto_expand_trigger ?? 0) + 1;
      if (mode === "k_only") {
        searchStats.auto_expand_k_only = (searchStats.auto_expand_k_only ?? 0) + 1;
      } else {
        searchStats.auto_expand_with_ab = (searchStats.auto_expand_with_ab ?? 0) + 1;
      }

      const forcedCornerKey = curGraph.activeVertices.has(need.needCornerV)
        ? pointKey(curGraph.points[need.needCornerV])
        : null;
      const expanded = makeGridGraph({
        corners,
        initialCornerEdgePairs,
        initialSegments: initialSeedSegments,
        aMax: target.targetA,
        bMax: target.targetB,
        kMax: target.targetK,
        cornerMaxDeg: config.cornerMaxDeg,
        minCornerLines: config.minCornerLines,
        enforceSymmetry: config.enforceSymmetry,
        useLocalRayDirty: config.useLocalRayDirty,
        seedStats: undefined,
        seedDirectCornerConnections,
        addSegmentWithSplitsIds,
      });
      remapGraphToNewGrid(curGraph, expanded.graph);
      let nextGraph = expanded.graph;
      const nextCornerIds = expanded.cornerIds;

      if (forcedCornerKey !== null && need.needCornerD >= 0) {
        searchStats.auto_expand_seed_attempt = (searchStats.auto_expand_seed_attempt ?? 0) + 1;
        const forcedV = nextGraph.pointToId.get(forcedCornerKey);
        if (forcedV === undefined || !nextGraph.activeVertices.has(forcedV)) {
          searchStats.auto_expand_seed_no_vertex = (searchStats.auto_expand_seed_no_vertex ?? 0) + 1;
        } else if (usedDirIndices(nextGraph, forcedV, false).has(need.needCornerD)) {
          searchStats.auto_expand_seed_used_dir = (searchStats.auto_expand_seed_used_dir ?? 0) + 1;
        } else {
          const forcedH = applyRayAction(nextGraph, {
            vIdx: forcedV,
            dirIdx: need.needCornerD,
            enforceSymmetry: config.enforceSymmetry,
            stats: searchStats,
          });
          if (forcedH === null) {
            searchStats.auto_expand_seed_fail = (searchStats.auto_expand_seed_fail ?? 0) + 1;
          } else if (config.requireCornerKawasaki) {
            const ckBefore = priorityCornerKawasakiScore(nextGraph, nextCornerIds, {
              tol: config.kawasakiTol,
            });
            const ckAfter = priorityCornerKawasakiScore(forcedH, nextCornerIds, {
              tol: config.kawasakiTol,
            });
            if (
              ckAfter[0] > ckBefore[0] ||
              (ckAfter[0] === ckBefore[0] && ckAfter[1] > ckBefore[1] + 1e-12)
            ) {
              searchStats.auto_expand_seed_reject_corner_kawasaki =
                (searchStats.auto_expand_seed_reject_corner_kawasaki ?? 0) + 1;
            } else {
              nextGraph = forcedH;
              searchStats.auto_expand_seed_success =
                (searchStats.auto_expand_seed_success ?? 0) + 1;
            }
          } else {
            nextGraph = forcedH;
            searchStats.auto_expand_seed_success = (searchStats.auto_expand_seed_success ?? 0) + 1;
          }
        }
      }

      aWork = target.targetA;
      bWork = target.targetB;
      aNormWork = target.targetANorm;
      bNormWork = target.targetBNorm;
      kLocal = target.targetK;
      curGraph = nextGraph;
      curCornerIds = nextCornerIds;
      stallStreak = 0;
      stageLogs.push({
        type: "auto_expand",
        reason: need.reason,
        required_corner_count: need.needCount,
        required_corner_v: need.needCornerV,
        required_corner_d: need.needCornerD,
        mode,
        a_max: aWork,
        b_max: bWork,
        a_norm: aNormWork,
        b_norm: bNormWork,
        k_max: kLocal,
        stats: graphStats(curGraph),
      });
    }

    effectiveK = kLocal;

    stageLogs.push({
      k: kCur,
      a_max: aWork,
      b_max: bWork,
      a_norm: aNormWork,
      b_norm: bNormWork,
      corner_score: {
        violations: curCornerIds.filter(
          (v) => cornerConditionError(curGraph, v, config.cornerMaxDeg) > 1e-12,
        ).length,
      },
      kawasaki_score: kawasakiScore(curGraph, { tol: config.kawasakiTol }),
      stats: graphStats(curGraph),
    });
  }

  if (
    config.finalPrune &&
    config.finalPruneRounds > 0 &&
    config.finalPruneMaxCandidates > 0
  ) {
    const pruned = applyFinalPruneRounds(curGraph, curCornerIds, {
      cornerMaxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
      kawasakiTol: config.kawasakiTol,
      enforceSymmetry: config.enforceSymmetry,
      finalPruneRounds: config.finalPruneRounds,
      finalPruneMaxCandidates: config.finalPruneMaxCandidates,
      searchStats,
    });
    curGraph = pruned.graph;
    stageLogs.push(...pruned.stageLogs);
  }

  const graph = buildMemGraphFromGrid(
    curGraph,
    curCornerIds,
    config,
    {
      aWork,
      bWork,
      aNormWork,
      bNormWork,
    },
    searchStats,
    stageLogs,
    kStartEffective,
    effectiveK,
    seedExpandRounds,
  );

  const cornerViolationsAfter = curCornerIds.filter(
    (v) => cornerConditionError(curGraph, v, config.cornerMaxDeg) > 1e-12,
  ).length;
  const kawasakiViolationsAfter = kawasakiScore(curGraph, {
    tol: config.kawasakiTol,
  })[0];
  const priorityCornerKawasakiViolationsAfter = priorityCornerKawasakiScore(
    curGraph,
    curCornerIds,
    { tol: config.kawasakiTol },
  )[0];

  const sec = (Date.now() - t0) / 1000.0;
  return {
    sec,
    graph,
    metrics: {
      cornerViolationsAfter,
      kawasakiViolationsAfter,
      priorityCornerKawasakiViolationsAfter,
    },
  };
}
