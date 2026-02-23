import { cpGraphV1ToMemGraph } from "./cp_graph_adapters";
import { CP_GRAPH_FIXTURE_SQUARE } from "./cp_graph_adapters_fixtures";
import { estimateFoldedPreview } from "./fold_preview";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

export function runFoldPreviewFixture(): void {
  const graph = cpGraphV1ToMemGraph(CP_GRAPH_FIXTURE_SQUARE);
  const out = estimateFoldedPreview({
    graph,
    alpha: 0.28,
    lineWidth: 0.9,
    showFaceId: false,
  });

  assert(out.stats.segmentCount === 4, "segment count mismatch");
  assert(out.stats.faceCount >= 1, "face count mismatch");
  assert(out.facePolygons.length >= 1, "no output polygons");
}

