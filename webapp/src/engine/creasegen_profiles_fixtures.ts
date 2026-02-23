import {
  compareCreasegenSummaries,
  evaluateCreasegenProfile,
  evaluateCreasegenProfiles,
  evaluateCreasegenProfilesWithBest,
  pickBestCreasegenEvaluation,
  REAL_DATA_BASELINE_NO_PRUNE_PROFILE,
  REAL_DATA_DRAFT_GUIDED_PROFILE,
  summarizeCreasegenResult,
} from "./creasegen_profiles";
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

export function runCreasegenProfilesFixture(): void {
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

  const evaluations = evaluateCreasegenProfiles({
    corners,
    profiles: [REAL_DATA_BASELINE_NO_PRUNE_PROFILE, REAL_DATA_DRAFT_GUIDED_PROFILE],
    baseConfig: {
      aMax: 1,
      bMax: 1,
      kMax: 1,
      maxDepth: 2,
      branchPerNode: 2,
      maxNodes: 80,
      enforceSymmetry: true,
      seedAutoExpand: false,
      autoExpandMaxRounds: 1,
      finalPruneRounds: 1,
      finalPruneMaxCandidates: 32,
      draftMaxDepth: 1,
      draftBranchPerNode: 1,
      draftMaxNodes: 40,
    },
  });

  assertCondition(evaluations.length === 2, "expected two profile evaluations");
  const base = evaluations[0];
  const draft = evaluations[1];
  assertCondition(base.profile.name === "baseline_no_prune", "baseline profile name mismatch");
  assertCondition(base.resolvedConfig.finalPrune === false, "baseline should disable prune");
  assertCondition(
    base.summary.finalPruneAppliedRounds === 0,
    "baseline should not apply final prune rounds",
  );
  assertCondition(
    draft.resolvedConfig.draftGuided === true,
    "draft-guided profile should enable draftGuided",
  );
  assertCondition(
    Number.isFinite(base.summary.sec) && base.summary.sec >= 0,
    "summary.sec must be finite non-negative",
  );

  const baseSummary = summarizeCreasegenResult(base.result);
  const draftSummary = summarizeCreasegenResult(draft.result);
  const cmp = compareCreasegenSummaries(baseSummary, draftSummary);
  assertCondition(
    cmp >= -1 && cmp <= 1,
    "summary comparator should produce a bounded ordering value",
  );

  const singleEval = evaluateCreasegenProfile({
    corners,
    seedSegments: [{ from: corners[0], to: corners[3] }],
    profile: REAL_DATA_BASELINE_NO_PRUNE_PROFILE,
    baseConfig: {
      aMax: 1,
      bMax: 1,
      kMax: 1,
      maxDepth: 2,
      branchPerNode: 2,
      maxNodes: 80,
      enforceSymmetry: true,
      seedAutoExpand: false,
      autoExpandMaxRounds: 1,
      finalPruneRounds: 1,
      finalPruneMaxCandidates: 32,
      draftMaxDepth: 1,
      draftBranchPerNode: 1,
      draftMaxNodes: 40,
    },
  });
  assertCondition(
    singleEval.profile.name === "baseline_no_prune",
    "single profile eval mismatch",
  );
  assertCondition(singleEval.result.graph.stats.edgeCount > 0, "seed segment eval should produce edges");

  const withBest = evaluateCreasegenProfilesWithBest({
    corners,
    profiles: [REAL_DATA_BASELINE_NO_PRUNE_PROFILE, REAL_DATA_DRAFT_GUIDED_PROFILE],
    baseConfig: {
      aMax: 1,
      bMax: 1,
      kMax: 1,
      maxDepth: 2,
      branchPerNode: 2,
      maxNodes: 80,
      enforceSymmetry: true,
      seedAutoExpand: false,
      autoExpandMaxRounds: 1,
      finalPruneRounds: 1,
      finalPruneMaxCandidates: 32,
      draftMaxDepth: 1,
      draftBranchPerNode: 1,
      draftMaxNodes: 40,
    },
  });
  assertCondition(withBest.evaluations.length === 2, "withBest evaluations length mismatch");
  const bestByPicker = pickBestCreasegenEvaluation(withBest.evaluations);
  assertCondition(
    withBest.best?.profile.name === bestByPicker?.profile.name,
    "best picker mismatch",
  );
}
