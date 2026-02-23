import { runCreasegen } from "./creasegen";
import { resolveRunConfig } from "./defaults";
import type {
  CreaseBuildInput,
  CreaseRunResult,
  RunConfig,
  RunConfigInput,
} from "./types";

export interface CreasegenEvalProfile {
  name: string;
  description: string;
  config?: RunConfigInput;
}

export interface CreasegenRunSummary {
  sec: number;
  cornerViolationsAfter: number;
  kawasakiViolationsAfter: number;
  priorityCornerKawasakiViolationsAfter: number;
  vertexCount: number;
  edgeCount: number;
  boundaryEdgeCount: number;
  recurseCalls: number;
  visitedNodes: number;
  acceptedChildren: number;
  refreshApplied: number;
  refreshTrigger: number;
  finalPruneAppliedRounds: number;
  finalPruneRemovedEdges: number;
}

export interface CreasegenProfileEvaluation {
  profile: CreasegenEvalProfile;
  resolvedConfig: RunConfig;
  result: CreaseRunResult;
  summary: CreasegenRunSummary;
}

export interface EvaluateCreasegenProfilesInput {
  corners: CreaseBuildInput["corners"];
  originOffset?: CreaseBuildInput["originOffset"];
  seedEdges?: CreaseBuildInput["seedEdges"];
  seedSegments?: CreaseBuildInput["seedSegments"];
  tiling?: CreaseBuildInput["tiling"];
  baseConfig?: RunConfigInput;
  profiles?: readonly CreasegenEvalProfile[];
}

export interface EvaluateCreasegenProfileInput {
  corners: CreaseBuildInput["corners"];
  originOffset?: CreaseBuildInput["originOffset"];
  seedEdges?: CreaseBuildInput["seedEdges"];
  seedSegments?: CreaseBuildInput["seedSegments"];
  tiling?: CreaseBuildInput["tiling"];
  baseConfig?: RunConfigInput;
  profile: CreasegenEvalProfile;
}

function stat(stats: Record<string, number> | undefined, key: string): number {
  return stats?.[key] ?? 0;
}

export function summarizeCreasegenResult(result: CreaseRunResult): CreasegenRunSummary {
  return {
    sec: result.sec,
    cornerViolationsAfter: result.metrics.cornerViolationsAfter,
    kawasakiViolationsAfter: result.metrics.kawasakiViolationsAfter,
    priorityCornerKawasakiViolationsAfter:
      result.metrics.priorityCornerKawasakiViolationsAfter,
    vertexCount: result.graph.stats.vertexCount,
    edgeCount: result.graph.stats.edgeCount,
    boundaryEdgeCount: result.graph.stats.boundaryEdgeCount,
    recurseCalls: stat(result.graph.searchStats, "recurse_calls"),
    visitedNodes: stat(result.graph.searchStats, "visited_nodes"),
    acceptedChildren: stat(result.graph.searchStats, "accepted_children"),
    refreshApplied: stat(result.graph.searchStats, "refresh_applied"),
    refreshTrigger: stat(result.graph.searchStats, "refresh_trigger"),
    finalPruneAppliedRounds: stat(result.graph.searchStats, "final_prune_applied_rounds"),
    finalPruneRemovedEdges: stat(result.graph.searchStats, "final_prune_removed_edges"),
  };
}

export const REAL_DATA_BASELINE_NO_PRUNE_PROFILE: CreasegenEvalProfile = {
  name: "baseline_no_prune",
  description: "Recommended starting profile for real data checks. Keep prune disabled.",
  config: {
    stagedKRelax: true,
    autoExpandGrid: true,
    finalPrune: false,
    draftGuided: false,
  },
};

export const REAL_DATA_DRAFT_GUIDED_PROFILE: CreasegenEvalProfile = {
  name: "draft_guided_no_prune",
  description: "Enable draft-guided hints while keeping prune disabled.",
  config: {
    stagedKRelax: true,
    autoExpandGrid: true,
    finalPrune: false,
    draftGuided: true,
  },
};

export const REAL_DATA_FULL_WITH_PRUNE_PROFILE: CreasegenEvalProfile = {
  name: "full_with_prune",
  description: "Reference profile with prune enabled for later comparison.",
  config: {
    stagedKRelax: true,
    autoExpandGrid: true,
    finalPrune: true,
    draftGuided: true,
  },
};

export const DEFAULT_REAL_DATA_EVAL_PROFILES: readonly CreasegenEvalProfile[] = [
  REAL_DATA_BASELINE_NO_PRUNE_PROFILE,
  REAL_DATA_DRAFT_GUIDED_PROFILE,
  REAL_DATA_FULL_WITH_PRUNE_PROFILE,
];

export function resolveCreasegenEvalProfiles(
  profiles?: readonly CreasegenEvalProfile[],
): readonly CreasegenEvalProfile[] {
  return profiles ?? DEFAULT_REAL_DATA_EVAL_PROFILES;
}

export function evaluateCreasegenProfile(
  input: EvaluateCreasegenProfileInput,
): CreasegenProfileEvaluation {
  const mergedInput: RunConfigInput = {
    ...(input.baseConfig ?? {}),
    ...(input.profile.config ?? {}),
  };
  const resolved = resolveRunConfig(mergedInput);
  const result = runCreasegen({
    corners: input.corners,
    originOffset: input.originOffset,
    seedEdges: input.seedEdges,
    seedSegments: input.seedSegments,
    tiling: input.tiling,
    config: resolved,
  });
  return {
    profile: input.profile,
    resolvedConfig: resolved,
    result,
    summary: summarizeCreasegenResult(result),
  };
}

export function evaluateCreasegenProfiles(
  input: EvaluateCreasegenProfilesInput,
): CreasegenProfileEvaluation[] {
  const profiles = resolveCreasegenEvalProfiles(input.profiles);
  const out: CreasegenProfileEvaluation[] = [];
  for (const profile of profiles) {
    out.push(
      evaluateCreasegenProfile({
        profile,
        baseConfig: input.baseConfig,
        corners: input.corners,
        originOffset: input.originOffset,
        seedEdges: input.seedEdges,
        seedSegments: input.seedSegments,
        tiling: input.tiling,
      }),
    );
  }
  return out;
}

export function pickBestCreasegenEvaluation(
  evaluations: readonly CreasegenProfileEvaluation[],
): CreasegenProfileEvaluation | null {
  let best: CreasegenProfileEvaluation | null = null;
  for (const ev of evaluations) {
    if (best === null || compareCreasegenSummaries(ev.summary, best.summary) < 0) {
      best = ev;
    }
  }
  return best;
}

export function evaluateCreasegenProfilesWithBest(
  input: EvaluateCreasegenProfilesInput,
): {
  evaluations: CreasegenProfileEvaluation[];
  best: CreasegenProfileEvaluation | null;
  bestResult: CreaseRunResult | null;
} {
  const evaluations = evaluateCreasegenProfiles(input);
  const best = pickBestCreasegenEvaluation(evaluations);
  return {
    evaluations,
    best,
    bestResult: best?.result ?? null,
  };
}

export function compareCreasegenSummaries(
  lhs: CreasegenRunSummary,
  rhs: CreasegenRunSummary,
): number {
  const keys: Array<keyof CreasegenRunSummary> = [
    "cornerViolationsAfter",
    "kawasakiViolationsAfter",
    "priorityCornerKawasakiViolationsAfter",
    "sec",
    "edgeCount",
  ];
  for (const k of keys) {
    if (lhs[k] < rhs[k]) {
      return -1;
    }
    if (lhs[k] > rhs[k]) {
      return 1;
    }
  }
  return 0;
}
