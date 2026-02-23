import type {
  CreaseBuildInput,
  FoldPreviewInput,
  OrigamiEngine,
  TilingRunInput,
} from "./engine_types";
import type {
  ComputeCommand,
  EngineWorkerProgress,
  EngineWorkerRequest,
  EngineWorkerResponse,
  WorkerRequestPayloadByCommand,
  WorkerResultPayloadByCommand,
} from "./engine_worker_protocol";
import { nextRequestId } from "./engine_worker_protocol";

type PendingRequest<C extends ComputeCommand = ComputeCommand> = {
  command: C;
  resolve: (value: WorkerResultPayloadByCommand[C]) => void;
  reject: (reason?: unknown) => void;
};

export class WorkerOrigamiEngine implements OrigamiEngine {
  private readonly worker: Worker;
  private readonly pending = new Map<string, PendingRequest>();
  private readonly progressListeners = new Set<(ev: EngineWorkerProgress) => void>();

  constructor(worker: Worker) {
    this.worker = worker;
    this.worker.onmessage = (ev: MessageEvent<EngineWorkerResponse>) => {
      const msg = ev.data;
      if (!msg) {
        return;
      }
      if (msg.kind === "progress") {
        this.progressListeners.forEach((fn) => fn(msg));
        return;
      }
      if (msg.kind === "error") {
        const pending = this.pending.get(msg.requestId);
        if (!pending) {
          return;
        }
        this.pending.delete(msg.requestId);
        pending.reject(new Error(msg.message));
        return;
      }
      if (msg.kind === "result") {
        const pending = this.pending.get(msg.requestId);
        if (!pending) {
          return;
        }
        this.pending.delete(msg.requestId);
        if (msg.command === "cancel" || msg.command !== pending.command) {
          pending.reject(
            new Error(
              `worker protocol mismatch: expected ${pending.command}, got ${msg.command}`,
            ),
          );
          return;
        }
        pending.resolve(msg.payload as WorkerResultPayloadByCommand[typeof pending.command]);
      }
    };
  }

  onProgress(listener: (ev: EngineWorkerProgress) => void): () => void {
    this.progressListeners.add(listener);
    return () => {
      this.progressListeners.delete(listener);
    };
  }

  dispose(): void {
    this.worker.terminate();
    this.pending.forEach((p) => p.reject(new Error("worker disposed")));
    this.pending.clear();
    this.progressListeners.clear();
  }

  cancel(requestId: string): void {
    const msg: EngineWorkerRequest = {
      kind: "request",
      requestId: nextRequestId("cancel"),
      command: "cancel",
      payload: {
        targetRequestId: requestId,
      },
    };
    this.worker.postMessage(msg);
  }

  private request<C extends ComputeCommand>(
    command: C,
    payload: WorkerRequestPayloadByCommand[C],
  ): Promise<WorkerResultPayloadByCommand[C]> {
    const requestId = nextRequestId(command);
    const msg: EngineWorkerRequest = {
      kind: "request",
      requestId,
      command,
      payload,
    };
    return new Promise<WorkerResultPayloadByCommand[C]>((resolve, reject) => {
      this.pending.set(requestId, {
        command,
        resolve,
        reject,
      });
      this.worker.postMessage(msg);
    });
  }

  runTiling(input: TilingRunInput) {
    return this.request("runTiling", input);
  }

  runCreasegen(input: CreaseBuildInput) {
    return this.request("runCreasegen", input);
  }

  runPreview(input: FoldPreviewInput) {
    return this.request("runPreview", input);
  }

  runAll(input: {
    tiling: TilingRunInput;
    creaseConfig?: CreaseBuildInput["config"];
    preview: Omit<FoldPreviewInput, "graph">;
    corners: CreaseBuildInput["corners"];
  }) {
    return this.request("runAll", input);
  }
}
