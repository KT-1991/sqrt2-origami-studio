/// <reference lib="webworker" />

import type {
  CreaseBuildInput,
  CreaseRunResult,
  FoldPreviewInput,
  FoldPreviewResult,
  OrigamiEngine,
  TilingRunInput,
  TilingState,
} from "../engine/types";
import type {
  ComputeCommand,
  EngineWorkerError,
  EngineWorkerProgress,
  EngineWorkerRequest,
  EngineWorkerResponse,
  RunAllInput,
} from "../engine/worker_protocol";
import { resolveRunConfig, resolveTilingRunInput } from "../engine/defaults";
import { estimateFoldedPreview } from "../engine/fold_preview";
import { runCreasegen as runCreasegenImpl } from "../engine/creasegen";
import {
  evaluateCreasegenProfile,
  pickBestCreasegenEvaluation,
  resolveCreasegenEvalProfiles,
  type CreasegenProfileEvaluation,
} from "../engine/creasegen_profiles";
import { runTiling as runTilingImpl } from "../engine/tiling";

declare const self: DedicatedWorkerGlobalScope;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function stageFromCommand(command: ComputeCommand): "tiling" | "creasegen" | "preview" {
  if (command === "runCreasegen" || command === "runCreasegenProfiles") {
    return "creasegen";
  }
  if (command === "runPreview") {
    return "preview";
  }
  return "tiling";
}

class MockOrigamiEngine implements OrigamiEngine {
  async runTiling(input: TilingRunInput): Promise<TilingState> {
    // Keep input validation from defaults for consistent errors across stages.
    resolveTilingRunInput(input);
    return runTilingImpl(input);
  }

  async runCreasegen(input: CreaseBuildInput): Promise<CreaseRunResult> {
    resolveRunConfig(input.config);
    await sleep(10);
    return runCreasegenImpl(input);
  }

  async runPreview(input: FoldPreviewInput): Promise<FoldPreviewResult> {
    return estimateFoldedPreview(input);
  }

  async runAll(input: RunAllInput) {
    const tiling = await this.runTiling(input.tiling);
    const crease = await this.runCreasegen({
      corners: input.corners,
      originOffset: input.originOffset,
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

    if (req.command === "runCreasegenProfiles") {
      const profiles = resolveCreasegenEvalProfiles(req.payload.profiles);
      const evaluations: CreasegenProfileEvaluation[] = [];
      const total = profiles.length;
      if (total <= 0) {
        post({
          kind: "result",
          requestId: req.requestId,
          command: req.command,
          payload: {
            evaluations,
            best: null,
            bestResult: null,
          },
        });
        clearCancel(req.requestId);
        return;
      }
      postProgress(req.requestId, req.command, "creasegen", 0.0, "profile eval start");
      for (let i = 0; i < total; i += 1) {
        if (isCancelled(req.requestId)) {
          clearCancel(req.requestId);
          return;
        }
        const profile = profiles[i];
        postProgress(
          req.requestId,
          req.command,
          "creasegen",
          i / total,
          `profile ${i + 1}/${total}: ${profile.name}`,
        );
        const ev = evaluateCreasegenProfile({
          profile,
          baseConfig: req.payload.baseConfig,
          corners: req.payload.corners,
          originOffset: req.payload.originOffset,
          seedEdges: req.payload.seedEdges,
          seedSegments: req.payload.seedSegments,
          tiling: req.payload.tiling,
        });
        evaluations.push(ev);
      }
      if (isCancelled(req.requestId)) {
        clearCancel(req.requestId);
        return;
      }
      const best = pickBestCreasegenEvaluation(evaluations);
      postProgress(req.requestId, req.command, "creasegen", 1.0, "profile eval done");
      post({
        kind: "result",
        requestId: req.requestId,
        command: req.command,
        payload: {
          evaluations,
          best,
          bestResult: best?.result ?? null,
        },
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
      originOffset: req.payload.originOffset,
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
      showFaceId: req.payload.preview.showFaceId,
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




