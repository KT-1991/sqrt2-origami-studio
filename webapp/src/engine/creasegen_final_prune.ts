import { globalScore, priorityCornerKawasakiScore, preserveSatisfiedCorners } from "./creasegen_evaluation";
import type { GridCreaseGraph } from "./creasegen_graph";
import { graphStats } from "./creasegen_graph_ops";
import { HALF } from "./qsqrt2";
import { cornerScore } from "./creasegen_scoring";
import { refreshGraphByPruning, type PruneLineKey } from "./creasegen_prune_axes";

function priorityNonworse(
  after: [number, number],
  before: [number, number],
): boolean {
  return after[0] < before[0] || (after[0] === before[0] && after[1] <= before[1] + 1e-12);
}

export function applyFinalPruneRounds(
  best: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    cornerMaxDeg: number;
    minCornerLines: number;
    kawasakiTol: number;
    enforceSymmetry: boolean;
    finalPruneRounds: number;
    finalPruneMaxCandidates: number;
    searchStats: Record<string, number>;
  },
): { graph: GridCreaseGraph; stageLogs: Array<Record<string, unknown>> } {
  const stageLogs: Array<Record<string, unknown>> = [];
  if (opts.finalPruneRounds <= 0 || opts.finalPruneMaxCandidates <= 0) {
    return { graph: best, stageLogs };
  }

  const probeLineKey: PruneLineKey = {
    axis: 6,
    a: HALF.a,
    b: HALF.b,
    k: HALF.k,
  };

  let outBest = best;
  for (let r = 1; r <= opts.finalPruneRounds; r += 1) {
    const refreshed = refreshGraphByPruning(outBest, cornerIds, {
      maxDeg: opts.cornerMaxDeg,
      minCornerLines: opts.minCornerLines,
      kawasakiTol: opts.kawasakiTol,
      enforceSymmetry: opts.enforceSymmetry,
      maxCandidates: opts.finalPruneMaxCandidates,
      stats: opts.searchStats,
      probeLineKey,
    });
    if (refreshed.removed <= 0) {
      opts.searchStats.final_prune_nochange = (opts.searchStats.final_prune_nochange ?? 0) + 1;
      break;
    }

    const beforeSc = globalScore(outBest, cornerIds, {
      maxDeg: opts.cornerMaxDeg,
      minCornerLines: opts.minCornerLines,
      kawasakiTol: opts.kawasakiTol,
    });
    const afterSc = globalScore(refreshed.graph, cornerIds, {
      maxDeg: opts.cornerMaxDeg,
      minCornerLines: opts.minCornerLines,
      kawasakiTol: opts.kawasakiTol,
    });
    const beforeCk = priorityCornerKawasakiScore(outBest, cornerIds, {
      tol: opts.kawasakiTol,
    });
    const afterCk = priorityCornerKawasakiScore(refreshed.graph, cornerIds, {
      tol: opts.kawasakiTol,
    });
    const beforeCorner = cornerScore(outBest, cornerIds, {
      maxDeg: opts.cornerMaxDeg,
      minCornerLines: opts.minCornerLines,
    });
    const afterCorner = cornerScore(refreshed.graph, cornerIds, {
      maxDeg: opts.cornerMaxDeg,
      minCornerLines: opts.minCornerLines,
    });

    const globalNonworse = afterSc[0] <= beforeSc[0] && afterSc[3] <= beforeSc[3] + 1e-12;
    const cornerNonworse =
      afterCorner[0] <= beforeCorner[0] &&
      afterCorner[1] <= beforeCorner[1] &&
      afterCorner[2] <= beforeCorner[2] + 1e-12 &&
      afterCorner[3] <= beforeCorner[3] + 1e-12;
    const keepSatisfied = preserveSatisfiedCorners(outBest, refreshed.graph, cornerIds, {
      maxDeg: opts.cornerMaxDeg,
      minCornerLines: opts.minCornerLines,
    });

    if (
      globalNonworse &&
      cornerNonworse &&
      keepSatisfied &&
      priorityNonworse(afterCk, beforeCk)
    ) {
      outBest = refreshed.graph;
      opts.searchStats.final_prune_applied_rounds =
        (opts.searchStats.final_prune_applied_rounds ?? 0) + 1;
      opts.searchStats.final_prune_removed_edges =
        (opts.searchStats.final_prune_removed_edges ?? 0) + refreshed.removed;
      stageLogs.push({
        type: "final_prune",
        round: r,
        removed_edges: refreshed.removed,
        score: afterSc,
        priority_corner_kawasaki: afterCk,
        stats: graphStats(outBest),
      });
      continue;
    }

    if (!cornerNonworse || !keepSatisfied) {
      opts.searchStats.final_prune_reject_corner_break =
        (opts.searchStats.final_prune_reject_corner_break ?? 0) + 1;
    }
    opts.searchStats.final_prune_reject_worse =
      (opts.searchStats.final_prune_reject_worse ?? 0) + 1;
  }

  return {
    graph: outBest,
    stageLogs,
  };
}
