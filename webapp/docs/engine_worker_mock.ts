/// <reference lib="webworker" />

import type {
  CreaseBuildInput,
  CreaseRunResult,
  FoldPreviewInput,
  FoldPreviewResult,
  OrigamiEngine,
  PointE,
  TilingRunInput,
  TilingState,
  Vec2,
} from "./engine_types";
import type {
  ComputeCommand,
  EngineWorkerError,
  EngineWorkerProgress,
  EngineWorkerRequest,
  EngineWorkerResponse,
  RunAllInput,
} from "./engine_worker_protocol";
import { resolveRunConfig, resolveTilingRunInput } from "./engine_defaults";

declare const self: DedicatedWorkerGlobalScope;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function qApprox(z: { a: bigint; b: bigint; k: number }): number {
  const num = Number(z.a) + Number(z.b) * Math.SQRT2;
  return num / 2 ** z.k;
}

function pointApprox(p: PointE): Vec2 {
  return { x: qApprox(p.x), y: qApprox(p.y) };
}

function stageFromCommand(command: ComputeCommand): "tiling" | "creasegen" | "preview" {
  if (command === "runCreasegen") {
    return "creasegen";
  }
  if (command === "runPreview") {
    return "preview";
  }
  return "tiling";
}

class MockOrigamiEngine implements OrigamiEngine {
  async runTiling(input: TilingRunInput): Promise<TilingState> {
    const resolved = resolveTilingRunInput(input);
    const specs = resolved.specs;
    const centers: Record<string, Vec2> = {};
    const n = Math.max(1, specs.length);
    for (let i = 0; i < specs.length; i += 1) {
      const t = (i + 1) / (n + 1);
      centers[specs[i].name] = { x: t, y: t };
    }
    const den = resolved.denCandidates[0];
    const coeff = resolved.coeffCandidates[0];
    const out: TilingState = {
      ok: true,
      alpha: 0.2,
      den,
      coeffLimit: coeff,
      centers,
      cornerHits: 4,
      contactScore: 0.0,
      message: "mock result",
    };
    await sleep(10);
    return out;
  }

  async runCreasegen(input: CreaseBuildInput): Promise<CreaseRunResult> {
    const config = resolveRunConfig(input.config);
    const corners = input.corners;
    if (corners.length < 3) {
      throw new Error("corners must have at least 3 points");
    }
    const vertices = corners.map((p, i) => {
      const approx = pointApprox(p);
      return {
        id: i,
        point: p,
        pointApprox: approx,
        isCorner: true,
        isBoundary: true,
      };
    });
    const edges = [] as Array<{
      id: number;
      v0: number;
      v1: number;
      isBoundary: boolean;
      axis8: number;
      birthOrder: number;
    }>;
    for (let i = 0; i < vertices.length; i += 1) {
      const j = (i + 1) % vertices.length;
      edges.push({
        id: i,
        v0: i,
        v1: j,
        isBoundary: true,
        axis8: 0,
        birthOrder: i,
      });
    }
    await sleep(10);
    return {
      sec: 0.02,
      graph: {
        schema: "cp_graph_mem_v1",
        vertices,
        edges,
        corners: vertices.map((v) => v.id),
        stats: {
          vertexCount: vertices.length,
          edgeCount: edges.length,
          boundaryEdgeCount: edges.length,
          cornerCount: vertices.length,
        },
        params: config,
      },
      metrics: {
        cornerViolationsAfter: 0,
        kawasakiViolationsAfter: 0,
        priorityCornerKawasakiViolationsAfter: 0,
      },
    };
  }

  async runPreview(input: FoldPreviewInput): Promise<FoldPreviewResult> {
    const poly = input.graph.vertices.map((v) => ({
      x: v.pointApprox.x,
      y: v.pointApprox.y,
    }));
    await sleep(10);
    return {
      facePolygons: [
        {
          faceId: 0,
          points: poly,
          depth: 0,
          frontSide: true,
        },
      ],
      stats: {
        segmentCount: input.graph.edges.length,
        faceCount: 1,
        dualEdgeCount: 0,
        transformInconsistencies: 0,
      },
    };
  }

  async runAll(input: RunAllInput) {
    const tiling = await this.runTiling(input.tiling);
    const crease = await this.runCreasegen({
      corners: input.corners,
      config: input.creaseConfig,
      tiling,
    });
    const preview = await this.runPreview({
      graph: crease.graph,
      alpha: input.preview.alpha,
      lineWidth: input.preview.lineWidth,
      showFaceId: input.preview.showFaceId,
    });
    return { tiling, crease, preview };
  }
}

const engine = new MockOrigamiEngine();
const cancelled = new Set<string>();

function post(msg: EngineWorkerResponse): void {
  self.postMessage(msg);
}

function postProgress(
  requestId: string,
  command: ComputeCommand,
  stage: "tiling" | "creasegen" | "preview",
  ratio: number,
  message?: string,
): void {
  const progress: EngineWorkerProgress = {
    kind: "progress",
    requestId,
    command,
    stage,
    ratio,
    message,
  };
  post(progress);
}

function postError(
  requestId: string,
  command: ComputeCommand,
  message: string,
): void {
  const err: EngineWorkerError = {
    kind: "error",
    requestId,
    command,
    stage: stageFromCommand(command),
    code: "INTERNAL",
    message,
    detail: {
      source: "engine_worker_mock",
    },
  };
  post(err);
}

function isCancelled(requestId: string): boolean {
  return cancelled.has(requestId);
}

function clearCancel(requestId: string): void {
  cancelled.delete(requestId);
}

self.onmessage = async (ev: MessageEvent<EngineWorkerRequest>) => {
  const req = ev.data;
  if (!req || req.kind !== "request") {
    return;
  }

  if (req.command === "cancel") {
    const target = req.payload.targetRequestId;
    if (target) {
      cancelled.add(target);
    }
    post({
      kind: "result",
      requestId: req.requestId,
      command: "cancel",
      payload: {
        accepted: true,
        targetRequestId: target,
      },
    });
    return;
  }

  try {
    if (req.command === "runTiling") {
      postProgress(req.requestId, req.command, "tiling", 0.0, "tiling start");
      const payload = await engine.runTiling(req.payload);
      if (isCancelled(req.requestId)) {
        clearCancel(req.requestId);
        return;
      }
      postProgress(req.requestId, req.command, "tiling", 1.0, "tiling done");
      post({
        kind: "result",
        requestId: req.requestId,
        command: req.command,
        payload,
      });
      clearCancel(req.requestId);
      return;
    }

    if (req.command === "runCreasegen") {
      postProgress(req.requestId, req.command, "creasegen", 0.0, "creasegen start");
      const payload = await engine.runCreasegen(req.payload);
      if (isCancelled(req.requestId)) {
        clearCancel(req.requestId);
        return;
      }
      postProgress(req.requestId, req.command, "creasegen", 1.0, "creasegen done");
      post({
        kind: "result",
        requestId: req.requestId,
        command: req.command,
        payload,
      });
      clearCancel(req.requestId);
      return;
    }

    if (req.command === "runPreview") {
      postProgress(req.requestId, req.command, "preview", 0.0, "preview start");
      const payload = await engine.runPreview(req.payload);
      if (isCancelled(req.requestId)) {
        clearCancel(req.requestId);
        return;
      }
      postProgress(req.requestId, req.command, "preview", 1.0, "preview done");
      post({
        kind: "result",
        requestId: req.requestId,
        command: req.command,
        payload,
      });
      clearCancel(req.requestId);
      return;
    }

    postProgress(req.requestId, req.command, "tiling", 0.0, "pipeline start");
    const tiling = await engine.runTiling(req.payload.tiling);
    if (isCancelled(req.requestId)) {
      clearCancel(req.requestId);
      return;
    }
    postProgress(req.requestId, req.command, "tiling", 1.0, "tiling done");

    postProgress(req.requestId, req.command, "creasegen", 0.0, "creasegen start");
    const crease = await engine.runCreasegen({
      corners: req.payload.corners,
      config: req.payload.creaseConfig,
      tiling,
    });
    if (isCancelled(req.requestId)) {
      clearCancel(req.requestId);
      return;
    }
    postProgress(req.requestId, req.command, "creasegen", 1.0, "creasegen done");

    postProgress(req.requestId, req.command, "preview", 0.0, "preview start");
    const preview = await engine.runPreview({
      graph: crease.graph,
      alpha: req.payload.preview.alpha,
      lineWidth: req.payload.preview.lineWidth,
      showFaceId: req.payload.showFaceId,
    });
    if (isCancelled(req.requestId)) {
      clearCancel(req.requestId);
      return;
    }
    postProgress(req.requestId, req.command, "preview", 1.0, "preview done");

    post({
      kind: "result",
      requestId: req.requestId,
      command: req.command,
      payload: {
        tiling,
        crease,
        preview,
      },
    });
    clearCancel(req.requestId);
  } catch (err) {
    clearCancel(req.requestId);
    const message = err instanceof Error ? err.message : String(err);
    postError(req.requestId, req.command, message);
  }
};
