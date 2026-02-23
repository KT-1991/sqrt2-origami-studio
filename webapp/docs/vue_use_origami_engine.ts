/*
  Vue integration sketch for WorkerOrigamiEngine.
  This is a usage sample, not framework-coupled runtime code.
*/

import { ref } from "vue";
import type {
  FoldPreviewResult,
  TilingState,
} from "./engine_types";
import { WorkerOrigamiEngine } from "./engine_client";

export function useOrigamiEngine(workerUrl: URL) {
  const worker = new Worker(workerUrl, { type: "module" });
  const engine = new WorkerOrigamiEngine(worker);

  const busy = ref(false);
  const progress = ref(0);
  const stage = ref<"tiling" | "creasegen" | "preview" | null>(null);
  const tiling = ref<TilingState | null>(null);
  const preview = ref<FoldPreviewResult | null>(null);
  const lastError = ref<string | null>(null);

  const off = engine.onProgress((ev) => {
    if (ev.kind !== "progress") {
      return;
    }
    progress.value = ev.ratio;
    stage.value = ev.stage;
  });

  async function runPipeline(input: Parameters<typeof engine.runAll>[0]) {
    busy.value = true;
    progress.value = 0;
    stage.value = null;
    lastError.value = null;
    try {
      const out = await engine.runAll(input);
      tiling.value = out.tiling;
      preview.value = out.preview;
      return out;
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : String(err);
      throw err;
    } finally {
      busy.value = false;
    }
  }

  function dispose() {
    off();
    engine.dispose();
  }

  return {
    busy,
    progress,
    stage,
    tiling,
    preview,
    lastError,
    runPipeline,
    dispose,
  };
}
