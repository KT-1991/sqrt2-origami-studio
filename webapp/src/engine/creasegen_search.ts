import {
  angleOfDirIdx,
  dirGapSteps,
  inCcwInterval,
  nearestDirIdx,
} from "./creasegen_direction";
import {
  globalScore,
  kawasakiResidualFromDirs,
  priorityCornerKawasakiScore,
  violatingVertexPriority,
} from "./creasegen_evaluation";
import { GridCreaseGraph } from "./creasegen_graph";
import { cloneGraph } from "./creasegen_graph_ops";
import { pointKey } from "./creasegen_grid_utils";
import { isBoundaryVertex, onDiagVertex } from "./creasegen_predicates";
import {
  childSortKey,
  refreshAcceptable,
  priorityCornerNonworse,
  pruneReason,
  scoreRejectReason,
  solvedByScore,
  type PriorityCornerTuple,
  type ScoreTuple,
} from "./creasegen_search_policy";
import { cornerLineCount, interiorWedge } from "./creasegen_scoring";
import type { RunConfig } from "./types";
import { ANGLE_COUNT, DIRS_F, mirroredDirIdx } from "./qsqrt2";
import { applyCandidateAction, applyRayAction } from "./creasegen_actions";
import { refreshGraphByPruning } from "./creasegen_prune_axes";

export type PreferredDirHints = Record<string, number[]>;

function edgeDirFrom(g: GridCreaseGraph, vIdx: number, uIdx: number): number {
  const bucket = g.edgeDirBucketAt(vIdx, uIdx);
  if (bucket !== undefined && bucket !== null) {
    const [vx, vy] = g.pointsF[vIdx];
    const [ux, uy] = g.pointsF[uIdx];
    const [bx, by] = DIRS_F[bucket];
    const dx = ux - vx;
    const dy = uy - vy;
    if (dx * bx + dy * by >= 0.0) {
      return bucket;
    }
    return (bucket + ANGLE_COUNT / 2) % ANGLE_COUNT;
  }
  const [vx, vy] = g.pointsF[vIdx];
  const [ux, uy] = g.pointsF[uIdx];
  return nearestDirIdx(ux - vx, uy - vy);
}

function usedDirIndices(
  g: GridCreaseGraph,
  vIdx: number,
  includeBoundary = false,
): Set<number> {
  const out = new Set<number>();
  for (const u of g.adj.get(vIdx) ?? []) {
    if (!includeBoundary && g.isBoundaryEdge(vIdx, u)) {
      continue;
    }
    out.add(edgeDirFrom(g, vIdx, u));
  }
  return out;
}

function admissibleDirsForVertex(
  g: GridCreaseGraph,
  vIdx: number,
  enforceSymmetry: boolean,
): number[] {
  let dirs = Array.from({ length: ANGLE_COUNT }, (_, i) => i);
  const [px, py] = g.pointsF[vIdx];
  const [start, width] = interiorWedge(px, py, 1e-10);
  if (width < 2.0 * Math.PI - 1e-10) {
    const end = start + width;
    dirs = dirs.filter((d) => inCcwInterval(angleOfDirIdx(d), start, end));
  }

  if (enforceSymmetry && onDiagVertex(g, vIdx)) {
    const out: number[] = [];
    const seen = new Set<string>();
    for (const d of dirs) {
      const md = (4 - d + ANGLE_COUNT) % ANGLE_COUNT;
      const a = Math.min(d, md);
      const b = Math.max(d, md);
      const key = `${a},${b}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      if (d === md) {
        continue;
      }
      out.push(a);
    }
    dirs = out;
  }
  return dirs;
}

function topkDirsForVertex(
  g: GridCreaseGraph,
  opts: {
    vIdx: number;
    dirs: readonly number[];
    usedDirs: ReadonlySet<number>;
    k: number;
    firstHitMap?: Readonly<Record<number, number | null>>;
  },
): number[] {
  if (opts.k <= 0 || opts.dirs.length <= opts.k) {
    return [...opts.dirs];
  }
  const usedSorted = [...opts.usedDirs].sort((a, b) => a - b);
  const scored: Array<[number, number, number, number]> = [];
  for (const d of opts.dirs) {
    const local = [...new Set([...opts.usedDirs, d])].sort((a, b) => a - b);
    const ke = kawasakiResidualFromDirs(local);
    const hitV = opts.firstHitMap?.[d] ?? g.rayNextAt(opts.vIdx, d);
    const bpen = hitV !== null && hitV !== undefined && isBoundaryVertex(g, hitV) ? 1 : 0;
    const gap = usedSorted.length > 0 ? Math.min(...usedSorted.map((ud) => dirGapSteps(d, ud))) : 0;
    scored.push([ke, bpen, gap, d]);
  }
  scored.sort((lhs, rhs) => {
    if (lhs[0] !== rhs[0]) {
      return lhs[0] - rhs[0];
    }
    if (lhs[1] !== rhs[1]) {
      return lhs[1] - rhs[1];
    }
    if (lhs[2] !== rhs[2]) {
      return lhs[2] - rhs[2];
    }
    return lhs[3] - rhs[3];
  });
  return scored.slice(0, opts.k).map((s) => s[3]);
}

function collectTrialDirs(
  state: GridCreaseGraph,
  opts: {
    vIdx: number;
    dirTopK: number;
    enforceSymmetry: boolean;
    stats: Record<string, number>;
    preferredDirs?: readonly number[];
  },
): {
  trialDirs: number[];
  firstHitMap: Record<number, number | null>;
  mirrorV: number | null;
  mirrorRow: Array<number | null> | null;
} | null {
  const used = usedDirIndices(state, opts.vIdx, false);
  const feasibleDirs: number[] = [];
  const firstHitMap: Record<number, number | null> = {};
  const rowV = state.ensureRayNext(opts.vIdx);
  for (const d of admissibleDirsForVertex(state, opts.vIdx, opts.enforceSymmetry)) {
    opts.stats.candidate_dirs_total = (opts.stats.candidate_dirs_total ?? 0) + 1;
    if (used.has(d)) {
      opts.stats.reject_used_dir = (opts.stats.reject_used_dir ?? 0) + 1;
      continue;
    }
    const hitV = rowV[d];
    if (hitV === null) {
      opts.stats.reject_no_ray_hit = (opts.stats.reject_no_ray_hit ?? 0) + 1;
      continue;
    }
    feasibleDirs.push(d);
    firstHitMap[d] = hitV;
  }
  if (feasibleDirs.length === 0) {
    return null;
  }

  let trialDirs = topkDirsForVertex(state, {
    vIdx: opts.vIdx,
    dirs: feasibleDirs,
    usedDirs: used,
    k: opts.dirTopK,
    firstHitMap,
  });
  if (trialDirs.length < feasibleDirs.length) {
    opts.stats.reject_topk_drop =
      (opts.stats.reject_topk_drop ?? 0) + (feasibleDirs.length - trialDirs.length);
  }

  if (opts.preferredDirs && opts.preferredDirs.length > 0) {
    const preferredOrder: number[] = [];
    const seenPreferred = new Set<number>();
    const feasibleSet = new Set(feasibleDirs);
    for (const d of opts.preferredDirs) {
      if (seenPreferred.has(d)) {
        continue;
      }
      seenPreferred.add(d);
      if (feasibleSet.has(d)) {
        preferredOrder.push(d);
      }
    }
    if (preferredOrder.length > 0) {
      opts.stats.hint_preferred_vertex = (opts.stats.hint_preferred_vertex ?? 0) + 1;
      const cap = opts.dirTopK > 0 ? opts.dirTopK : feasibleDirs.length;
      const merged: number[] = [];
      for (const d of preferredOrder) {
        merged.push(d);
        if (merged.length >= cap) {
          break;
        }
      }
      if (merged.length < cap) {
        for (const d of trialDirs) {
          if (merged.includes(d)) {
            continue;
          }
          merged.push(d);
          if (merged.length >= cap) {
            break;
          }
        }
      }
      const hintUsed = merged.filter((d) => seenPreferred.has(d)).length;
      if (hintUsed > 0) {
        opts.stats.hint_preferred_dir_used =
          (opts.stats.hint_preferred_dir_used ?? 0) + hintUsed;
      }
      trialDirs = merged;
    }
  }

  let mirrorV: number | null = null;
  let mirrorRow: Array<number | null> | null = null;
  if (opts.enforceSymmetry) {
    mirrorV = state.mirrorVertexIdx(opts.vIdx);
    if (mirrorV !== null) {
      mirrorRow = state.ensureRayNext(mirrorV);
    }
  }

  return { trialDirs, firstHitMap, mirrorV, mirrorRow };
}

function moveEquivalenceKey(
  opts: {
    vIdx: number;
    dirIdx: number;
    firstHitMap: Record<number, number | null>;
    enforceSymmetry: boolean;
    mirrorV: number | null;
    mirrorRow: Array<number | null> | null;
  },
): string | null {
  const firstHit = opts.firstHitMap[opts.dirIdx];
  if (firstHit === null || firstHit === undefined) {
    return null;
  }
  const firstKey = `V:${firstHit}`;
  let mirrorKey: string | null = null;
  if (opts.enforceSymmetry) {
    if (opts.mirrorV === null) {
      mirrorKey = "MISSING_MIRROR_VERTEX";
    } else {
      const md = mirroredDirIdx(opts.dirIdx);
      const mhit = opts.mirrorRow?.[md] ?? null;
      mirrorKey = mhit === null ? null : `V:${mhit}`;
    }
  }
  return `${opts.vIdx}|${firstKey}|${mirrorKey ?? "N"}`;
}

function singleRayGrowthClass(
  g: GridCreaseGraph,
  originV: number,
  dirIdx: number,
): number {
  const hit = g.rayHitAt(originV, dirIdx);
  if (hit === null) {
    return 2;
  }
  const [, , hitPos, p] = hit;
  if (hitPos !== 0) {
    return 0;
  }
  const hitV = g.pointToId.get(pointKey(p));
  if (hitV === undefined) {
    return 2;
  }
  if (g.activeVertices.has(hitV)) {
    return 0;
  }
  return 1;
}

function moveStructureTier(
  g: GridCreaseGraph,
  opts: {
    vIdx: number;
    dirIdx: number;
    cornerSet: ReadonlySet<number>;
    enforceSymmetry: boolean;
  },
): number {
  if (opts.cornerSet.has(opts.vIdx)) {
    return 2;
  }
  let grow = singleRayGrowthClass(g, opts.vIdx, opts.dirIdx);
  if (opts.enforceSymmetry) {
    const mv = g.mirrorVertexIdx(opts.vIdx);
    if (mv === null) {
      return 3;
    }
    const md = mirroredDirIdx(opts.dirIdx);
    grow = Math.max(grow, singleRayGrowthClass(g, mv, md));
  }
  if (grow <= 0) {
    return 0;
  }
  if (grow === 1) {
    return 1;
  }
  return 3;
}

function compareScore(
  a: ScoreTuple,
  b: ScoreTuple,
): number {
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] < b[i]) {
      return -1;
    }
    if (a[i] > b[i]) {
      return 1;
    }
  }
  return 0;
}

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

function stateKeyString(g: GridCreaseGraph): string {
  const [h1, h2, m] = g.stateKey();
  return `${h1.toString(16)}:${h2.toString(16)}:${m}`;
}

export function runGreedyRepair(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  config: RunConfig,
  searchStats?: Record<string, number>,
): GridCreaseGraph {
  let state = g;
  let nodes = 0;
  let bestScore = globalScore(state, cornerIds, {
    maxDeg: config.cornerMaxDeg,
    minCornerLines: config.minCornerLines,
    kawasakiTol: config.kawasakiTol,
  });
  searchStats = searchStats ?? {};

  const maxDepth = Math.max(0, config.maxDepth);
  for (let depth = 0; depth < maxDepth; depth += 1) {
    searchStats.greedy_depth_round = (searchStats.greedy_depth_round ?? 0) + 1;
    const priority = violatingVertexPriority(state, cornerIds, {
      maxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
      kawasakiTol: config.kawasakiTol,
    });
    if (priority.length === 0) {
      searchStats.greedy_early_solved = (searchStats.greedy_early_solved ?? 0) + 1;
      break;
    }

    let bestChild: GridCreaseGraph | null = null;
    let bestChildScore: [number, number, number, number, number, number] | null = null;
    const focus = priority.slice(0, Math.max(1, config.priorityTopN));
    for (const v of focus) {
      const used = usedDirIndices(state, v, false);
      const rowV = state.ensureRayNext(v);
      const feasible: number[] = [];
      const firstHitMap: Record<number, number | null> = {};
      for (const d of admissibleDirsForVertex(state, v, config.enforceSymmetry)) {
        searchStats.candidate_dirs_total = (searchStats.candidate_dirs_total ?? 0) + 1;
        if (used.has(d)) {
          searchStats.reject_used_dir = (searchStats.reject_used_dir ?? 0) + 1;
          continue;
        }
        const hitV = rowV[d];
        if (hitV === null) {
          searchStats.reject_no_ray_hit = (searchStats.reject_no_ray_hit ?? 0) + 1;
          continue;
        }
        feasible.push(d);
        firstHitMap[d] = hitV;
      }
      if (feasible.length === 0) {
        continue;
      }
      const trialDirs = topkDirsForVertex(state, {
        vIdx: v,
        dirs: feasible,
        usedDirs: used,
        k: config.dirTopK,
        firstHitMap,
      });
      if (trialDirs.length < feasible.length) {
        searchStats.reject_topk_drop =
          (searchStats.reject_topk_drop ?? 0) + (feasible.length - trialDirs.length);
      }

      for (const d of trialDirs) {
        nodes += 1;
        searchStats.greedy_node_eval = (searchStats.greedy_node_eval ?? 0) + 1;
        if (nodes > config.maxNodes) {
          searchStats.prune_max_nodes = (searchStats.prune_max_nodes ?? 0) + 1;
          break;
        }
        const h = applyRayAction(state, {
          vIdx: v,
          dirIdx: d,
          enforceSymmetry: config.enforceSymmetry,
          stats: searchStats,
        });
        if (h === null) {
          searchStats.reject_action_failed = (searchStats.reject_action_failed ?? 0) + 1;
          continue;
        }
        const score = globalScore(h, cornerIds, {
          maxDeg: config.cornerMaxDeg,
          minCornerLines: config.minCornerLines,
          kawasakiTol: config.kawasakiTol,
        });
        if (bestChildScore === null || compareScore(score, bestChildScore) < 0) {
          bestChild = h;
          bestChildScore = score;
        }
      }
      if (nodes > config.maxNodes) {
        break;
      }
    }

    if (bestChild === null || bestChildScore === null) {
      searchStats.greedy_stall = (searchStats.greedy_stall ?? 0) + 1;
      break;
    }
    if (compareScore(bestChildScore, bestScore) < 0) {
      state = bestChild;
      bestScore = bestChildScore;
      searchStats.greedy_accept = (searchStats.greedy_accept ?? 0) + 1;
    } else {
      searchStats.greedy_no_improve = (searchStats.greedy_no_improve ?? 0) + 1;
      break;
    }
    if (nodes > config.maxNodes) {
      break;
    }
  }
  return state;
}

export function runDfsRepair(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  config: RunConfig,
  searchStats?: Record<string, number>,
  preferredDirHints?: PreferredDirHints | null,
): GridCreaseGraph {
  const stats = searchStats ?? {};
  const scoreCache = new Map<string, ScoreTuple>();
  const priorityCache = new Map<string, PriorityCornerTuple>();

  function inc(key: string, n = 1): void {
    stats[key] = (stats[key] ?? 0) + n;
  }

  function cachedGlobalScore(state: GridCreaseGraph): ScoreTuple {
    const sk = stateKeyString(state);
    const cached = scoreCache.get(sk);
    if (cached !== undefined) {
      return cached;
    }
    const sc = globalScore(state, cornerIds, {
      maxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
      kawasakiTol: config.kawasakiTol,
    });
    scoreCache.set(sk, sc);
    return sc;
  }

  function cachedPriorityCornerKawasaki(state: GridCreaseGraph): PriorityCornerTuple {
    const sk = stateKeyString(state);
    const cached = priorityCache.get(sk);
    if (cached !== undefined) {
      return cached;
    }
    const ck = priorityCornerKawasakiScore(state, cornerIds, {
      tol: config.kawasakiTol,
    });
    priorityCache.set(sk, ck);
    return ck;
  }

  let best = cloneGraph(g);
  let bestScore = cachedGlobalScore(best);
  const cornerSet = new Set<number>(cornerIds);
  const seen = new Set<string>([stateKeyString(g)]);
  let nodeCounter = 0;
  let solved = false;
  const refreshEveryNodes = 30;
  const refreshMaxCandidates = 24;

  function recurse(state: GridCreaseGraph, depth: number): void {
    inc("recurse_calls");
    if (solved) {
      inc("prune_already_solved");
      return;
    }
    nodeCounter += 1;
    inc("visited_nodes");
    if (nodeCounter > config.maxNodes) {
      inc("prune_max_nodes");
      return;
    }

    let sc = cachedGlobalScore(state);
    if (compareScore(sc, bestScore) < 0) {
      best = cloneGraph(state);
      bestScore = sc;
    }
    if (config.stopOnCornerClear && sc[1] === 0) {
      solved = true;
      inc("stopped_corner_clear");
      best = cloneGraph(state);
      bestScore = sc;
      return;
    }

    let ck = cachedPriorityCornerKawasaki(state);
    if (solvedByScore(sc, ck, { requireCornerKawasaki: config.requireCornerKawasaki })) {
      solved = true;
      inc("solved_nodes");
      best = cloneGraph(state);
      bestScore = sc;
      return;
    }

    const pReason = pruneReason(sc, {
      depth,
      maxDepth: config.maxDepth,
      allowViolations: config.allowViolations,
    });
    if (pReason !== null) {
      if (pReason === "max_depth") {
        inc("prune_max_depth");
      } else {
        inc("prune_allow_violations");
      }
      return;
    }

    if (refreshEveryNodes > 0 && depth > 0 && nodeCounter % refreshEveryNodes === 0) {
      inc("refresh_trigger");
      const refreshed = refreshGraphByPruning(state, cornerIds, {
        maxDeg: config.cornerMaxDeg,
        minCornerLines: config.minCornerLines,
        kawasakiTol: config.kawasakiTol,
        enforceSymmetry: config.enforceSymmetry,
        maxCandidates: refreshMaxCandidates,
        stats,
      });
      if (refreshed.removed > 0) {
        const rKey = stateKeyString(refreshed.graph);
        if (seen.has(rKey)) {
          inc("refresh_reject_seen");
        } else {
          const rSc = cachedGlobalScore(refreshed.graph);
          const rCk = cachedPriorityCornerKawasaki(refreshed.graph);
          if (
            refreshAcceptable(sc, ck, rSc, rCk, {
              requireCornerKawasaki: config.requireCornerKawasaki,
            })
          ) {
            seen.add(rKey);
            state = refreshed.graph;
            sc = rSc;
            ck = rCk;
            inc("refresh_applied");
            inc("refresh_removed_edges", refreshed.removed);
            if (compareScore(sc, bestScore) < 0) {
              best = cloneGraph(state);
              bestScore = sc;
            }
          } else {
            inc("refresh_reject_worse");
          }
        }
      } else {
        inc("refresh_nochange");
      }
    }

    const priority = violatingVertexPriority(state, cornerIds, {
      maxDeg: config.cornerMaxDeg,
      minCornerLines: config.minCornerLines,
      kawasakiTol: config.kawasakiTol,
    });

    const childPool: Array<{
      key: [number, number, number, number, number, number, number, number];
      state: GridCreaseGraph;
    }> = [];
    const seenMoveEquiv = new Set<string>();
    const focus = priority.slice(0, Math.max(1, config.priorityTopN));
    for (const v of focus) {
      const preferredDirs =
        preferredDirHints?.[pointKey(state.points[v])];
      const trialPack = collectTrialDirs(state, {
        vIdx: v,
        dirTopK: config.dirTopK,
        enforceSymmetry: config.enforceSymmetry,
        stats,
        preferredDirs,
      });
      if (trialPack === null) {
        continue;
      }
      const { trialDirs, firstHitMap, mirrorV, mirrorRow } = trialPack;

      for (const d of trialDirs) {
        const mk = moveEquivalenceKey({
          vIdx: v,
          dirIdx: d,
          firstHitMap,
          enforceSymmetry: config.enforceSymmetry,
          mirrorV,
          mirrorRow,
        });
        if (mk === null) {
          inc("reject_no_first_hit");
          continue;
        }
        if (seenMoveEquiv.has(mk)) {
          inc("reject_equiv_move");
          continue;
        }
        seenMoveEquiv.add(mk);

        const moveTier = moveStructureTier(state, {
          vIdx: v,
          dirIdx: d,
          cornerSet,
          enforceSymmetry: config.enforceSymmetry,
        });

        const h = applyCandidateAction(state, {
          vIdx: v,
          dirIdx: d,
          enableOpenSink: config.enableOpenSink,
          enableOpenSinkRepair: config.enableOpenSinkRepair,
          enableCornerKawasakiRepair: config.enableCornerKawasakiRepair,
          enforceSymmetry: config.enforceSymmetry,
          openSinkMaxBounces: config.openSinkMaxBounces,
          kawasakiTol: config.kawasakiTol,
          cornerIds,
          stats,
        });
        if (h === null) {
          inc("reject_action_failed");
          continue;
        }
        const sk = stateKeyString(h);
        if (seen.has(sk)) {
          inc("reject_seen_state");
          continue;
        }
        seen.add(sk);

        const hsc = cachedGlobalScore(h);
        const rejectReason = scoreRejectReason(sc, hsc, { margin: 2 });
        if (rejectReason === "kawasaki") {
          inc("reject_score_bad_kawasaki");
          continue;
        }
        if (rejectReason === "corner") {
          inc("reject_score_bad_corner");
          continue;
        }
        if (rejectReason === "lowline") {
          inc("reject_score_bad_lowline");
          continue;
        }
        if (config.requireCornerKawasaki) {
          const hck = cachedPriorityCornerKawasaki(h);
          if (!priorityCornerNonworse(ck, hck)) {
            inc("reject_priority_corner_kawasaki");
            continue;
          }
        }
        const key = childSortKey(sc, hsc, moveTier);
        inc("accepted_children");
        childPool.push({ key, state: h });
      }
    }

    childPool.sort((lhs, rhs) => compareNumericTuple(lhs.key, rhs.key));
    if (childPool.length > config.branchPerNode) {
      inc("prune_branch_limit", childPool.length - config.branchPerNode);
    }

    for (let i = 0; i < Math.min(config.branchPerNode, childPool.length); i += 1) {
      recurse(childPool[i].state, depth + 1);
    }
  }

  recurse(g, 0);
  return best;
}

export function summarizeCornerLineCounts(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
): number[] {
  return cornerIds.map((v) => cornerLineCount(g, v));
}
