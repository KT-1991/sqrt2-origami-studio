import {
  DEFAULT_RUN_CONFIG,
  DEFAULT_TILING_OPTIONS,
  RunConfig,
  RunConfigInput,
  TilingRunInput,
  TilingRunInputResolved,
} from "./engine_types";

function assertPositiveInt(value: number, field: string): void {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${field} must be a positive integer`);
  }
}

function assertNonNegativeNumber(value: number, field: string): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new Error(`${field} must be a non-negative finite number`);
  }
}

function assertIntArray(values: number[], field: string): void {
  if (values.length === 0) {
    throw new Error(`${field} must not be empty`);
  }
  for (const v of values) {
    assertPositiveInt(v, field);
  }
}

export function resolveRunConfig(input?: RunConfigInput): RunConfig {
  const out: RunConfig = {
    ...DEFAULT_RUN_CONFIG,
    ...(input ?? {}),
  };

  assertPositiveInt(out.aMax, "aMax");
  assertPositiveInt(out.bMax, "bMax");
  assertPositiveInt(out.kMax, "kMax");
  assertPositiveInt(out.maxDepth, "maxDepth");
  assertPositiveInt(out.branchPerNode, "branchPerNode");
  assertPositiveInt(out.maxNodes, "maxNodes");
  assertPositiveInt(out.openSinkMaxBounces, "openSinkMaxBounces");
  assertPositiveInt(out.minCornerLines, "minCornerLines");
  assertPositiveInt(out.kStart, "kStart");
  assertPositiveInt(out.dirTopK, "dirTopK");
  assertPositiveInt(out.priorityTopN, "priorityTopN");
  assertPositiveInt(out.autoExpandMaxRounds, "autoExpandMaxRounds");
  assertPositiveInt(out.expandStallRounds, "expandStallRounds");
  assertPositiveInt(out.seedAutoExpandMaxRounds, "seedAutoExpandMaxRounds");
  assertPositiveInt(out.finalPruneRounds, "finalPruneRounds");
  assertPositiveInt(out.finalPruneMaxCandidates, "finalPruneMaxCandidates");
  assertPositiveInt(out.pruneAxesMax, "pruneAxesMax");
  assertPositiveInt(out.draftMaxDepth, "draftMaxDepth");
  assertPositiveInt(out.draftBranchPerNode, "draftBranchPerNode");
  assertPositiveInt(out.draftMaxNodes, "draftMaxNodes");
  assertNonNegativeNumber(out.cornerMaxDeg, "cornerMaxDeg");
  assertNonNegativeNumber(out.kawasakiTol, "kawasakiTol");

  return out;
}

export function resolveTilingRunInput(input: TilingRunInput): TilingRunInputResolved {
  if (!input.specs || input.specs.length === 0) {
    throw new Error("specs must not be empty");
  }

  const out: TilingRunInputResolved = {
    specs: input.specs,
    denCandidates: input.denCandidates ?? DEFAULT_TILING_OPTIONS.denCandidates,
    coeffCandidates: input.coeffCandidates ?? DEFAULT_TILING_OPTIONS.coeffCandidates,
    seed: input.seed ?? DEFAULT_TILING_OPTIONS.seed,
    alphaSteps: input.alphaSteps ?? DEFAULT_TILING_OPTIONS.alphaSteps,
    packRestarts: input.packRestarts ?? DEFAULT_TILING_OPTIONS.packRestarts,
    packIters: input.packIters ?? DEFAULT_TILING_OPTIONS.packIters,
    packGuidedRestarts:
      input.packGuidedRestarts ?? DEFAULT_TILING_OPTIONS.packGuidedRestarts,
    packGuidedJitter: input.packGuidedJitter ?? DEFAULT_TILING_OPTIONS.packGuidedJitter,
    warmStart: input.warmStart ?? DEFAULT_TILING_OPTIONS.warmStart,
    initialCenters: input.initialCenters,
    initialIndependent: input.initialIndependent,
  };

  assertIntArray(out.denCandidates, "denCandidates");
  assertIntArray(out.coeffCandidates, "coeffCandidates");
  assertPositiveInt(out.alphaSteps, "alphaSteps");
  assertPositiveInt(out.packRestarts, "packRestarts");
  assertPositiveInt(out.packIters, "packIters");
  assertNonNegativeNumber(out.packGuidedJitter, "packGuidedJitter");
  if (!Number.isInteger(out.seed)) {
    throw new Error("seed must be an integer");
  }

  return out;
}
