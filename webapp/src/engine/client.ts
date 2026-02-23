import type {
  CreaseBuildInput,
  FoldPreviewInput,
  OrigamiEngine,
  TilingRunInput,
} from "./types";
import type {
  ComputeCommand,
  EngineWorkerProgress,
  EngineWorkerRequest,
  EngineWorkerResponse,
  WorkerRequestPayloadByCommand,
  WorkerResultPayloadByCommand,
} from "./worker_protocol";
import { nextRequestId } from "./worker_protocol";

interface PendingRequest {
  command: ComputeCommand;
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
}

function toWorkerCloneSafe<T>(value: T, seen = new Map<object, unknown>()): T {
  if (value === null || value === undefined) {
    return value;
  }
  const t = typeof value;
  if (t !== "object") {
    return value;
  }

  if (value instanceof Date) {
    return new Date(value.getTime()) as T;
  }
  if (value instanceof ArrayBuffer) {
    return value.slice(0) as T;
  }
  if (ArrayBuffer.isView(value)) {
    return value as T;
  }

  const obj = value as object;
  const memo = seen.get(obj);
  if (memo !== undefined) {
    return memo as T;
  }

  if (Array.isArray(value)) {
    const out: unknown[] = [];
    seen.set(obj, out);
    for (const item of value) {
      out.push(toWorkerCloneSafe(item, seen));
    }
    return out as T;
  }

  if (value instanceof Map) {
    const out = new Map<unknown, unknown>();
    seen.set(obj, out);
    for (const [k, v] of value.entries()) {
      out.set(toWorkerCloneSafe(k, seen), toWorkerCloneSafe(v, seen));
    }
    return out as T;
  }

  if (value instanceof Set) {
    const out = new Set<unknown>();
    seen.set(obj, out);
    for (const v of value.values()) {
      out.add(toWorkerCloneSafe(v, seen));
    }
    return out as T;
  }

  const out: Record<string, unknown> = {};
  seen.set(obj, out);
  for (const key of Object.keys(value as Record<string, unknown>)) {
    out[key] = toWorkerCloneSafe(
      (value as Record<string, unknown>)[key],
      seen,
    );
  }
  return out as T;
}

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
        pending.resolve(msg.payload);
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
    const safePayload = toWorkerCloneSafe(payload);
    const msg = {
      kind: "request",
      requestId,
      command,
      payload: safePayload,
    } as Extract<EngineWorkerRequest, { command: C }>;

    return new Promise<WorkerResultPayloadByCommand[C]>((resolve, reject) => {
      this.pending.set(requestId, {
        command,
        resolve: (value) => resolve(value as WorkerResultPayloadByCommand[C]),
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

  runCreasegenProfiles(input: WorkerRequestPayloadByCommand["runCreasegenProfiles"]) {
    return this.request("runCreasegenProfiles", input);
  }

  runAll(input: {
    tiling: TilingRunInput;
    creaseConfig?: CreaseBuildInput["config"];
    preview: Omit<FoldPreviewInput, "graph">;
    corners: CreaseBuildInput["corners"];
    originOffset?: CreaseBuildInput["originOffset"];
  }) {
    return this.request("runAll", input);
  }
}
