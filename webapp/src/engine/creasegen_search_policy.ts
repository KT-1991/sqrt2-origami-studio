export type ScoreTuple = [number, number, number, number, number, number];
export type PriorityCornerTuple = [number, number];

export function solvedByScore(
  score: ScoreTuple,
  priorityCornerKawasaki: PriorityCornerTuple,
  opts: {
    requireCornerKawasaki: boolean;
  },
): boolean {
  return (
    score[0] === 0 &&
    score[1] === 0 &&
    score[2] === 0 &&
    (priorityCornerKawasaki[0] === 0 || !opts.requireCornerKawasaki)
  );
}

export function pruneReason(
  score: ScoreTuple,
  opts: {
    depth: number;
    maxDepth: number;
    allowViolations: number;
  },
): "max_depth" | "allow_violations" | null {
  if (opts.depth >= opts.maxDepth) {
    return "max_depth";
  }
  if (score[0] === 0 && score[1] <= opts.allowViolations && score[2] === 0) {
    return "allow_violations";
  }
  return null;
}

export function priorityCornerNonworse(
  beforePriorityCornerKawasaki: PriorityCornerTuple,
  afterPriorityCornerKawasaki: PriorityCornerTuple,
): boolean {
  return afterPriorityCornerKawasaki[0] <= beforePriorityCornerKawasaki[0];
}

export function refreshAcceptable(
  beforeScore: ScoreTuple,
  beforePriorityCornerKawasaki: PriorityCornerTuple,
  afterScore: ScoreTuple,
  afterPriorityCornerKawasaki: PriorityCornerTuple,
  opts: {
    requireCornerKawasaki: boolean;
  },
): boolean {
  return (
    afterScore[0] <= beforeScore[0] &&
    afterScore[1] <= beforeScore[1] &&
    afterScore[2] <= beforeScore[2] &&
    afterScore[3] <= beforeScore[3] + 1e-12 &&
    afterScore[4] <= beforeScore[4] + 1e-12 &&
    afterScore[5] <= beforeScore[5] + 1e-12 &&
    (!opts.requireCornerKawasaki ||
      afterPriorityCornerKawasaki[0] <= beforePriorityCornerKawasaki[0])
  );
}

export function scoreRejectReason(
  parentScore: ScoreTuple,
  childScore: ScoreTuple,
  opts: {
    margin: number;
  },
): "kawasaki" | "corner" | "lowline" | null {
  if (childScore[0] > parentScore[0] + opts.margin) {
    return "kawasaki";
  }
  if (childScore[1] > parentScore[1] + opts.margin) {
    return "corner";
  }
  if (childScore[2] > parentScore[2] + opts.margin) {
    return "lowline";
  }
  return null;
}

export function childSortKey(
  parentScore: ScoreTuple,
  childScore: ScoreTuple,
  moveTier: number,
): [number, number, number, number, number, number, number, number] {
  const kIncrease = childScore[0] > parentScore[0] ? 1 : 0;
  return [kIncrease, moveTier, ...childScore];
}
