import { GridCreaseGraph } from "./creasegen_graph";
import { cloneGraph } from "./creasegen_graph_ops";
import {
  diagonalSymmetryOk,
  isBoundaryVertex,
  onDiagVertex,
} from "./creasegen_predicates";
import { pointKey } from "./creasegen_grid_utils";
import {
  angleOfDirIdx,
  dirGapSteps,
  inCcwInterval,
  nearestDirIdx,
  reflectedDirIdx,
  symmetricCandidateDirs,
} from "./creasegen_direction";
import {
  kawasakiResidualFromDirs,
  kawasakiTargetVertexIds,
  vertexKawasakiError,
} from "./creasegen_evaluation";
import { interiorWedge } from "./creasegen_scoring";
import { ANGLE_COUNT, mirroredDirIdx } from "./qsqrt2";

export function applyRayAction(
  g: GridCreaseGraph,
  opts: {
    vIdx: number;
    dirIdx: number;
    enforceSymmetry?: boolean;
    stats?: Record<string, number>;
  },
): GridCreaseGraph | null {
  const h = cloneGraph(g);
  if (h.shootRayAndSplit(opts.vIdx, opts.dirIdx, null, opts.stats) === null) {
    return null;
  }
  if (opts.enforceSymmetry ?? true) {
    const mv = h.mirrorVertexIdx(opts.vIdx);
    if (mv === null) {
      return null;
    }
    const md = mirroredDirIdx(opts.dirIdx);
    if (!(mv === opts.vIdx && md === opts.dirIdx)) {
      if (h.shootRayAndSplit(mv, md, null, opts.stats) === null) {
        return null;
      }
    }
    if (!diagonalSymmetryOk(h)) {
      return null;
    }
  }
  return h;
}

function incidentDirIndices(g: GridCreaseGraph, vIdx: number): number[] {
  const [vx, vy] = g.pointsF[vIdx];
  const out = new Set<number>();
  for (const u of g.adj.get(vIdx) ?? []) {
    const [ux, uy] = g.pointsF[u];
    out.add(nearestDirIdx(ux - vx, uy - vy));
  }
  return [...out].sort((a, b) => a - b);
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
      const md = mirroredDirIdx(d);
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

function runOpenSinkTransaction(
  g: GridCreaseGraph,
  frontsInit: Array<[number, number]>,
  opts: {
    enforceSymmetry: boolean;
    maxBounces: number;
    stats?: Record<string, number>;
  },
): GridCreaseGraph | null {
  if (frontsInit.length === 0) {
    return null;
  }
  const h = g;
  const rayVs = frontsInit.map((f) => f[0]);
  const rayDs = frontsInit.map((f) => f[1]);
  const rayDone = frontsInit.map(() => false);
  const configSeen = new Set<string>();

  function nextDirAtExistingVertex(vIdx: number, incomingD: number): number | null {
    const used = incidentDirIndices(h, vIdx);
    const admissible = admissibleDirsForVertex(h, vIdx, false);
    const cand = symmetricCandidateDirs(used, admissible, incomingD);
    if (cand.length === 0) {
      return null;
    }
    const scored: Array<[number, number, number, number]> = [];
    for (const d of cand) {
      const local = [...new Set([...used, d])].sort((a, b) => a - b);
      const ke = kawasakiResidualFromDirs(local);
      const sat = ke <= 1e-8 ? 0 : 1;
      scored.push([sat, ke, dirGapSteps(d, incomingD), d]);
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
    return scored[0][3];
  }

  function configKey(): string {
    const cur: Array<[number, number]> = [];
    for (let i = 0; i < rayVs.length; i += 1) {
      cur.push([rayVs[i], rayDone[i] ? -1 : rayDs[i]]);
    }
    cur.sort((lhs, rhs) => {
      if (lhs[0] !== rhs[0]) {
        return lhs[0] - rhs[0];
      }
      return lhs[1] - rhs[1];
    });
    return cur.map((c) => `${c[0]}:${c[1]}`).join("|");
  }

  configSeen.add(configKey());
  for (let bounce = 0; bounce < opts.maxBounces; bounce += 1) {
    for (let rid = 0; rid < rayVs.length; rid += 1) {
      if (rayDone[rid]) {
        continue;
      }
      const curV = rayVs[rid];
      const curD = rayDs[rid];
      const hit = h.firstHitEdge(curV, curD);
      if (hit === null) {
        return null;
      }
      const [i, j, hitPos, pHit] = hit;
      const aF = h.pointsF[i];
      const bF = h.pointsF[j];
      const hitInterior = hitPos === 0;

      if (h.shootRayAndSplit(curV, curD, hit, opts.stats) === null) {
        return null;
      }

      let nextV: number | undefined;
      if (hitPos < 0) {
        nextV = i;
      } else if (hitPos > 0) {
        nextV = j;
      } else {
        nextV = h.pointToId.get(pointKey(pHit));
      }
      if (nextV === undefined) {
        return null;
      }
      rayVs[rid] = nextV;

      if (onDiagVertex(h, nextV) || isBoundaryVertex(h, nextV)) {
        rayDone[rid] = true;
        continue;
      }

      if (hitInterior) {
        rayDs[rid] = reflectedDirIdx(curD, aF, bF);
      } else {
        const nd = nextDirAtExistingVertex(nextV, curD);
        if (nd === null) {
          return null;
        }
        rayDs[rid] = nd;
      }
    }

    const active = rayVs.filter((_, idx) => !rayDone[idx]);
    if (new Set(active).size !== active.length || rayDone.every(Boolean)) {
      break;
    }
    const c = configKey();
    if (configSeen.has(c)) {
      break;
    }
    configSeen.add(c);
  }

  if (opts.enforceSymmetry && !diagonalSymmetryOk(h)) {
    return null;
  }
  return h;
}

export function repairOpenSinkVertices(
  g: GridCreaseGraph,
  opts: {
    enforceSymmetry: boolean;
    maxBounces: number;
    tol?: number;
    maxRounds?: number;
    maxTryDirs?: number;
  },
): GridCreaseGraph {
  const tol = opts.tol ?? 1e-8;
  const maxRounds = opts.maxRounds ?? 2;
  const maxTryDirs = opts.maxTryDirs ?? 6;
  let h = g;

  for (let round = 0; round < maxRounds; round += 1) {
    const targets = kawasakiTargetVertexIds(h).filter((v) => vertexKawasakiError(h, v) > tol);
    if (targets.length === 0) {
      return h;
    }
    let progressed = false;

    for (const v of targets) {
      const beforeKe = vertexKawasakiError(h, v);
      const beforeTotal = kawasakiTargetVertexIds(h).reduce(
        (acc, u) => acc + vertexKawasakiError(h, u),
        0.0,
      );
      const used = incidentDirIndices(h, v);
      const admissible = admissibleDirsForVertex(h, v, opts.enforceSymmetry);
      const cand = symmetricCandidateDirs(used, admissible, undefined);
      if (cand.length === 0) {
        continue;
      }
      const sortedCand = [...cand]
        .sort((lhs, rhs) => {
          const lke = kawasakiResidualFromDirs([...new Set([...used, lhs])].sort((a, b) => a - b));
          const rke = kawasakiResidualFromDirs([...new Set([...used, rhs])].sort((a, b) => a - b));
          return lke - rke;
        })
        .slice(0, Math.max(1, maxTryDirs));

      let bestH: GridCreaseGraph | null = null;
      let bestKey: [number, number] | null = null;
      for (const d of sortedCand) {
        const hh = applyOpenSinkAction(h, {
          vIdx: v,
          dirIdx: d,
          enforceSymmetry: opts.enforceSymmetry,
          maxBounces: opts.maxBounces,
          enableRepair: false,
        });
        if (hh === null) {
          continue;
        }
        const afterKe = vertexKawasakiError(hh, v);
        const afterTotal = kawasakiTargetVertexIds(hh).reduce(
          (acc, u) => acc + vertexKawasakiError(hh, u),
          0.0,
        );
        const key: [number, number] = [afterKe, afterTotal];
        if (
          bestKey === null ||
          key[0] < bestKey[0] - 1e-12 ||
          (Math.abs(key[0] - bestKey[0]) <= 1e-12 && key[1] < bestKey[1] - 1e-12)
        ) {
          bestKey = key;
          bestH = hh;
        }
      }
      if (bestH === null || bestKey === null) {
        continue;
      }
      if (bestKey[0] < beforeKe - 1e-12 || bestKey[1] < beforeTotal - 1e-12) {
        h = bestH;
        progressed = true;
        break;
      }
    }

    if (!progressed) {
      break;
    }
  }
  return h;
}

export function repairPriorityCornersOpenSink(
  g: GridCreaseGraph,
  cornerIds: readonly number[],
  opts: {
    enforceSymmetry: boolean;
    maxBounces: number;
    tol?: number;
    maxRounds?: number;
    maxTryDirs?: number;
  },
): GridCreaseGraph {
  const tol = opts.tol ?? 1e-8;
  const maxRounds = opts.maxRounds ?? 2;
  const maxTryDirs = opts.maxTryDirs ?? 6;
  let h = g;
  const cset = cornerIds.filter((v) => h.activeVertices.has(v) && !isBoundaryVertex(h, v));
  if (cset.length === 0) {
    return h;
  }

  for (let round = 0; round < maxRounds; round += 1) {
    const targets = cset.filter((v) => vertexKawasakiError(h, v) > tol);
    if (targets.length === 0) {
      return h;
    }
    targets.sort((lhs, rhs) => vertexKawasakiError(h, rhs) - vertexKawasakiError(h, lhs));
    let progressed = false;

    for (const v of targets) {
      const beforeKe = vertexKawasakiError(h, v);
      const used = new Set(incidentDirIndices(h, v));
      const admissible = admissibleDirsForVertex(h, v, opts.enforceSymmetry);
      const cand = admissible.filter((d) => !used.has(d));
      if (cand.length === 0) {
        continue;
      }
      const sortedCand = [...cand]
        .sort((lhs, rhs) => {
          const lke = kawasakiResidualFromDirs([...new Set([...used, lhs])].sort((a, b) => a - b));
          const rke = kawasakiResidualFromDirs([...new Set([...used, rhs])].sort((a, b) => a - b));
          return lke - rke;
        })
        .slice(0, Math.max(1, maxTryDirs));

      let bestH: GridCreaseGraph | null = null;
      let bestKey: [number, number] | null = null;
      for (const d of sortedCand) {
        const hh = applyOpenSinkAction(h, {
          vIdx: v,
          dirIdx: d,
          enforceSymmetry: opts.enforceSymmetry,
          maxBounces: opts.maxBounces,
          enableRepair: false,
        });
        if (hh === null) {
          continue;
        }
        const afterKe = vertexKawasakiError(hh, v);
        const afterTotalCorner = cset.reduce((acc, u) => acc + vertexKawasakiError(hh, u), 0.0);
        const key: [number, number] = [afterKe, afterTotalCorner];
        if (
          bestKey === null ||
          key[0] < bestKey[0] - 1e-12 ||
          (Math.abs(key[0] - bestKey[0]) <= 1e-12 && key[1] < bestKey[1] - 1e-12)
        ) {
          bestKey = key;
          bestH = hh;
        }
      }
      if (bestH === null || bestKey === null) {
        continue;
      }
      if (bestKey[0] < beforeKe - 1e-12) {
        h = bestH;
        progressed = true;
        break;
      }
    }

    if (!progressed) {
      break;
    }
  }
  return h;
}

export function applyOpenSinkAction(
  g: GridCreaseGraph,
  opts: {
    vIdx: number;
    dirIdx: number;
    enforceSymmetry: boolean;
    maxBounces: number;
    enableRepair: boolean;
    tol?: number;
    inPlace?: boolean;
    stats?: Record<string, number>;
  },
): GridCreaseGraph | null {
  const h0 = opts.inPlace ? g : cloneGraph(g);
  const fronts: Array<[number, number]> = [[opts.vIdx, opts.dirIdx]];
  if (opts.enforceSymmetry) {
    const mv = h0.mirrorVertexIdx(opts.vIdx);
    if (mv === null) {
      return null;
    }
    fronts.push([mv, mirroredDirIdx(opts.dirIdx)]);
  }
  const uniq: Array<[number, number]> = [];
  const seen = new Set<string>();
  for (const [v, d] of fronts) {
    const key = `${v},${d}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    uniq.push([v, d]);
  }

  let out = runOpenSinkTransaction(h0, uniq, {
    enforceSymmetry: opts.enforceSymmetry,
    maxBounces: opts.maxBounces,
    stats: opts.stats,
  });
  if (out === null) {
    return null;
  }
  if (opts.enableRepair) {
    out = repairOpenSinkVertices(out, {
      enforceSymmetry: opts.enforceSymmetry,
      maxBounces: opts.maxBounces,
      tol: opts.tol,
    });
    if (opts.enforceSymmetry && !diagonalSymmetryOk(out)) {
      return null;
    }
  }
  return out;
}

export function applyCandidateAction(
  state: GridCreaseGraph,
  opts: {
    vIdx: number;
    dirIdx: number;
    enableOpenSink: boolean;
    enableOpenSinkRepair: boolean;
    enableCornerKawasakiRepair: boolean;
    enforceSymmetry: boolean;
    openSinkMaxBounces: number;
    kawasakiTol: number;
    cornerIds: readonly number[];
    stats: Record<string, number>;
  },
): GridCreaseGraph | null {
  if (opts.enableOpenSink) {
    let h = applyOpenSinkAction(state, {
      vIdx: opts.vIdx,
      dirIdx: opts.dirIdx,
      enforceSymmetry: opts.enforceSymmetry,
      maxBounces: opts.openSinkMaxBounces,
      enableRepair: opts.enableOpenSinkRepair,
      tol: opts.kawasakiTol,
      stats: opts.stats,
    });
    if (h === null) {
      return null;
    }
    if (opts.enableCornerKawasakiRepair) {
      h = repairPriorityCornersOpenSink(h, opts.cornerIds, {
        enforceSymmetry: opts.enforceSymmetry,
        maxBounces: opts.openSinkMaxBounces,
        tol: opts.kawasakiTol,
      });
    }
    return h;
  }

  return applyRayAction(state, {
    vIdx: opts.vIdx,
    dirIdx: opts.dirIdx,
    enforceSymmetry: opts.enforceSymmetry,
    stats: opts.stats,
  });
}
