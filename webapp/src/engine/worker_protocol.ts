import type {
  CreaseBuildInput,
  CreaseRunResult,
  CreaseSeedEdgeInput,
  CreaseSeedSegmentInput,
  EngineErrorEvent,
  EngineProgressEvent,
  FoldPreviewInput,
  FoldPreviewResult,
  PointE,
  RunConfigInput,
  TilingRunInput,
  TilingState,
} from "./types";
import type {
  CreasegenEvalProfile,
  CreasegenProfileEvaluation,
} from "./creasegen_profiles";

export type ComputeCommand =
  | "runTiling"
  | "runCreasegen"
  | "runPreview"
  | "runCreasegenProfiles"
  | "runAll";

export type WorkerCommand = ComputeCommand | "cancel";

export interface RunAllInput {
  tiling: TilingRunInput;
  creaseConfig?: RunConfigInput;
  preview: Omit<FoldPreviewInput, "graph">;
  corners: PointE[];
  originOffset?: PointE;
}

export interface RunCreasegenProfilesInput {
  corners: PointE[];
  originOffset?: PointE;
  seedEdges?: CreaseSeedEdgeInput[];
  seedSegments?: CreaseSeedSegmentInput[];
  tiling?: TilingState;
  baseConfig?: RunConfigInput;
  profiles?: readonly CreasegenEvalProfile[];
}

export interface WorkerRequestPayloadByCommand {
  runTiling: TilingRunInput;
  runCreasegen: CreaseBuildInput;
  runPreview: FoldPreviewInput;
  runCreasegenProfiles: RunCreasegenProfilesInput;
  runAll: RunAllInput;
  cancel: {
    targetRequestId?: string;
  };
}

export interface WorkerResultPayloadByCommand {
  runTiling: TilingState;
  runCreasegen: CreaseRunResult;
  runPreview: FoldPreviewResult;
  runCreasegenProfiles: {
    evaluations: CreasegenProfileEvaluation[];
    best: CreasegenProfileEvaluation | null;
    bestResult: CreaseRunResult | null;
  };
  runAll: {
    tiling: TilingState;
    crease: CreaseRunResult;
    preview: FoldPreviewResult;
  };
  cancel: {
    accepted: true;
    targetRequestId?: string;
  };
}

export type EngineWorkerRequest = {
  [C in WorkerCommand]: {
    kind: "request";
    requestId: string;
    command: C;
    payload: WorkerRequestPayloadByCommand[C];
  };
}[WorkerCommand];

export type EngineWorkerResult = {
  [C in WorkerCommand]: {
    kind: "result";
    requestId: string;
    command: C;
    payload: WorkerResultPayloadByCommand[C];
  };
}[WorkerCommand];

export interface EngineWorkerProgress extends EngineProgressEvent {
  command: ComputeCommand;
}

export interface EngineWorkerError extends EngineErrorEvent {
  command: ComputeCommand;
}

export type EngineWorkerResponse =
  | EngineWorkerProgress
  | EngineWorkerResult
  | EngineWorkerError;

export function nextRequestId(prefix = "req"): string {
  const rnd = Math.random().toString(36).slice(2, 8);
  const ts = Date.now().toString(36);
  return `${prefix}_${ts}_${rnd}`;
}
