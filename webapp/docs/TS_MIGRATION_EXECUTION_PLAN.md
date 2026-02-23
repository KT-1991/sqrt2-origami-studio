# TypeScript + Vue Static Web App Migration Plan

Last updated: 2026-02-20

## 0. Goal
Build a fully static, client-only web app for the origami pipeline.

Pipeline:
- Stage A: kado layout optimization (`tiling` equivalent)
- Stage B: crease pattern generation (`creasegen` equivalent)
- Stage C: folded preview estimation (`cp_fold_preview` equivalent)

Hard requirement:
- Runtime stage handoff must stay in memory (no JSON stringify/parse in hot path).

## 1. Architecture Principles
- Principle A: Separate runtime models from persistence models.
- Principle B: Use Web Worker for all heavy compute.
- Principle C: Keep deterministic behavior by explicit seeds and stable sorting.
- Principle D: Use JSON only for import/export, snapshots, and compatibility checks.
- Principle E: Keep UI isolated from algorithm internals through `engine` API.

## 2. Runtime Data Flow (No JSON in Hot Path)
- UI thread -> Worker: structured clone typed objects.
- Stage handoff inside Worker:
  - `TilingState` -> `CreaseBuildInput` -> `CreaseGraphMem` -> `FoldPreviewInput`.
- Worker -> UI thread:
  - `EngineProgressEvent` for progress.
  - `EngineResultEvent` for final typed result.

## 3. Milestones

### M1: Contract Lock (Models + API)
Scope:
- Freeze runtime models and persistence schemas.
- Add worker message protocol and error contract.

Exit criteria:
- `docs/engine_types.ts` accepted as baseline contract.
- No unresolved naming mismatch between Python concepts and TS models.

### M2: Vue + Worker Skeleton
Scope:
- Create Vue app shell, controls, and result panels.
- Implement worker bridge with mocked engine outputs.

Exit criteria:
- One-click pipeline run works with mock data.
- UI never blocks during mock compute.

### M3: Fold Preview Port (`cp_fold_preview`)
Scope:
- Port geometric face reconstruction and transform propagation.
- Render in Canvas/SVG (replace matplotlib logic).

Exit criteria:
- Same input graph yields visually equivalent folded preview.
- Core stats are within tolerance of Python version.

### M4: Tiling Port (`tiling`)
Scope:
- Port continuous pack, snapping, repair, and alpha search.

Exit criteria:
- Fixed-seed runs produce same feasibility and near-equivalent objective values.
- Stage handoff uses runtime objects only.

### M5: Crease Core Port (`creasegen` base)
Scope:
- Port exact number model (`Qsqrt2` with bigint), graph primitives, scoring kernels.

Exit criteria:
- Core graph operations and scoring pass golden tests vs Python outputs.

### M6: Crease Search Port (`creasegen` search/stage)
Scope:
- Port staged search pipeline, pruning, and final selection.

Exit criteria:
- Full pipeline runs in TS end-to-end with acceptable runtime.
- Representative benchmark cases produce comparable quality metrics.

### M7: Productization (Static Delivery)
Scope:
- Performance tuning, import/export UX, resumable run snapshots, offline support.

Exit criteria:
- Static hosting build works without server.
- User can run pipeline, preview result, and export project data locally.

## 4. Validation Strategy
- Golden fixtures:
  - Save Python outputs for fixed seeds and configs.
  - Compare TS outputs by normalized metrics and structural invariants.
- Determinism checks:
  - Fixed seed + fixed config must produce stable output hash.
- Performance checks:
  - Track stage runtime and peak memory in Worker.

## 5. Risk and Mitigation
- Risk: numeric drift from float-only math.
  - Mitigation: keep exact arithmetic (`Qsqrt2`) in bigint where required.
- Risk: UI freeze from heavy search.
  - Mitigation: all compute in Worker, chunk long loops for progress updates.
- Risk: migration stalls on `creasegen` complexity.
  - Mitigation: incremental parity tests and milestone gates above.

## 6. Immediate Next Tasks
1. Finalize field-level contracts in `docs/engine_types.ts`.
2. Implement Worker protocol shell with mock handlers.
3. Build a minimal Vue screen that executes mock `runAll` and displays typed results.

## 7. M1 Decisions (Locked)
- `TilingRunInput` and `RunConfigInput` are partial user-facing inputs.
- Execution always uses resolved forms:
  - `TilingRunInputResolved`
  - `RunConfig` (resolved)
- Default values are centralized in `docs/engine_types.ts`:
  - `DEFAULT_TILING_OPTIONS`
  - `DEFAULT_RUN_CONFIG`
- Schema conversion boundary is explicit:
  - `cpGraphV1ToMemGraph(...)`
  - `memGraphToCpGraphV1(...)`
- Rule: stage-to-stage runtime handoff must use `CreaseGraphMem` only.

## 8. Current Status
- M1 contract lock is now concrete in code-like artifacts:
  - `docs/engine_types.ts`
  - `docs/engine_defaults.ts`
  - `docs/cp_graph_adapters.ts`
- Next recommended move:
  1. Wire these files into actual Worker entrypoints.
  2. Add 2-3 fixture-based roundtrip tests for cp_graph conversion.

## 9. M2 Bootstrapping Artifacts
- Added worker protocol contract:
  - `docs/engine_worker_protocol.ts`
- Added mock worker implementation (message handler + progress/error/result):
  - `docs/engine_worker_mock.ts`
- Added client-side worker bridge implementing `OrigamiEngine`:
  - `docs/engine_client.ts`
- Added Vue composable sketch:
  - `docs/vue_use_origami_engine.ts`

These files are scaffolding for integration and can later be moved from `docs/` into the actual web app source tree.

## 10. Test Seed Artifacts
- Added a fixture-based roundtrip self-check:
  - `docs/cp_graph_adapters_fixtures.ts`
- Purpose:
  - protect schema conversion behavior before real TS implementation lands.
  - provide a simple baseline that can be moved into Vitest/Jest later.

## 11. Next Focus (from now)
1. Move files from `docs/` into actual app source tree (`src/engine` and `src/workers`).
2. Add real TypeScript build + typecheck (`tsconfig`, `vue-tsc` or `tsc --noEmit`).
3. Replace mock worker handlers with real Stage C (`cp_fold_preview`) port first.
4. Add fixture tests:
   - `cp_graph` roundtrip in test runner.
   - deterministic seed smoke test for `runTiling` contract.

## 12. Implementation Placement (Done)
- Promoted prototype files to runtime source tree:
  - `src/engine/types.ts`
  - `src/engine/defaults.ts`
  - `src/engine/cp_graph_adapters.ts`
  - `src/engine/cp_graph_adapters_fixtures.ts`
  - `src/engine/worker_protocol.ts`
  - `src/engine/client.ts`
  - `src/workers/origami_engine.worker.ts`
- Added barrel export:
  - `src/engine/index.ts`
- Added TypeScript config baseline:
  - `tsconfig.json`

Note:
- `tsc` is not installed globally in this environment yet, so typecheck execution remains pending.

## 13. Verification Status
- TypeScript check executed successfully on 2026-02-21:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Result:
  - no type errors in `src/engine/**` and `src/workers/**`.

## 14. Stage C Preview Port (Initial)
- Implemented geometric folded-preview core in TS:
  - `src/engine/fold_preview.ts`
- Worker `runPreview` now calls real geometry implementation:
  - `src/workers/origami_engine.worker.ts`
- Added minimal runtime fixture for preview:
  - `src/engine/fold_preview_fixtures.ts`

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture run:
  - `npm exec --yes --package tsx -- tsx --eval "import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); console.log('FOLD_PREVIEW_FIXTURE_OK');"`

## 15. Stage C Parity Check (Python vs TS)
Input:
- `_tmp_out/cp_graph_test2.json`

Python (`py/cp_fold_preview.py`) stats:
- `segment_count`: 28
- `face_count`: 16
- `dual_edge_count`: 20
- `transform_inconsistencies`: 4

TypeScript (`src/engine/fold_preview.ts`) stats:
- `segmentCount`: 28
- `faceCount`: 16
- `dualEdgeCount`: 20
- `transformInconsistencies`: 4

Result:
- stage C core geometry parity confirmed for this fixture.

## 16. Stage A Tiling Port (Initial)
- Implemented TS tiling core based on `py/tiling.py`:
  - `src/engine/tiling.ts`
- Worker `runTiling` now calls TS implementation:
  - `src/workers/origami_engine.worker.ts`
- Added deterministic fixture for tiling:
  - `src/engine/tiling_fixtures.ts`

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); console.log('TILING_FIXTURE_OK');"`
- Status:
  - TS implementation is deterministic for fixed seed and produces feasible solutions on baseline fixture.

Parity note:
- Python/TS outputs are both feasible on the checked two-axis input, but not bit-identical yet (expected at this stage).
- Remaining parity work: RNG alignment and tie-break/rounding-level reconciliation.

## 17. Stage B Foundation (Qsqrt2)
- Added exact arithmetic module for `(a + b*sqrt(2))/2^k`:
  - `src/engine/qsqrt2.ts`
- Added fixture checks for exact ops and direction constants:
  - `src/engine/qsqrt2_fixtures.ts`
- Integrated shared approximation helper into worker path:
  - `src/workers/origami_engine.worker.ts`

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- New fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); console.log('QSQRT2_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runTilingFixture(); runFoldPreviewFixture(); console.log('EXISTING_FIXTURES_OK');"`

## 18. Stage B Foundation (Grid Graph Core)
- Added `creasegen` utility modules:
  - `src/engine/creasegen_grid_utils.ts`
  - `src/engine/creasegen_direction.ts`
  - `src/engine/creasegen_geometry.ts`
- Added Stage B graph core:
  - `src/engine/creasegen_graph.ts`
  - includes `enumerateGridPoints(...)`, `GridCreaseGraph`, ray-hit cache, edge split insertion, and transaction scaffolding.
- Added graph operation wrappers:
  - `src/engine/creasegen_graph_ops.ts`
  - includes clone/adopt/state-key and grid remap/stat helpers.
- Added deterministic fixture:
  - `src/engine/creasegen_graph_fixtures.ts`
- Updated barrel export:
  - `src/engine/index.ts`

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- New graph fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runCreasegenGraphFixture(); console.log('CREASEGEN_GRAPH_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); console.log('REGRESSION_FIXTURES_OK');"`

Status:
- Stage B の探索ロジック本体（`search` / `stage_search`）は未移植。
- ただし、探索を載せるための格子グラフと幾何カーネルは TS 側で実行可能になった。

## 19. Stage B Seed Runtime (Worker Integration)
- Added Stage B seeding primitives and predicates:
  - `src/engine/creasegen_predicates.ts`
  - `src/engine/creasegen_seeding.ts`
- Added initial Stage B runtime entry:
  - `src/engine/creasegen.ts`
  - `runCreasegen(...)` now builds a real grid graph (boundary + seeded corner connections + diagonal seed) and emits `cp_graph_mem_v1`.
- Worker integration:
  - `src/workers/origami_engine.worker.ts`
  - `runCreasegen` path switched from mock polygon output to `runCreasegen(...)`.
- Added fixture:
  - `src/engine/creasegen_fixtures.ts`
- Barrel export updates:
  - `src/engine/index.ts`

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- New fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runCreasegenGraphFixture(); console.log('CREASEGEN_GRAPH_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on Python output corners:
  - `npm exec --yes --package tsx -- tsx --eval "import { readFileSync } from 'node:fs'; import { cpGraphV1ToMemGraph, runCreasegen } from './src/engine/index.ts'; const raw = JSON.parse(readFileSync('_tmp_out/cp_graph_test2.json','utf8')); const mem = cpGraphV1ToMemGraph(raw); const corners = mem.vertices.filter(v=>v.isCorner).map(v=>v.point); const out = runCreasegen({ corners, config: { aMax:2,bMax:2,kMax:2,enforceSymmetry:true,maxDepth:1,branchPerNode:2,maxNodes:64 } }); console.log('CREASEGEN_SMOKE', out.graph.stats.vertexCount, out.graph.stats.edgeCount, out.graph.stats.cornerCount);"`

Status:
- `runCreasegen` は mock 依存を脱却し、Stage B の「初期グラフ生成」まで実行可能。
- 未完了は DFS repair / staged search / final prune など探索本体。

## 20. Stage B Metrics Port (Scoring/Evaluation)
- Added corner scoring module:
  - `src/engine/creasegen_scoring.ts`
  - ported `incident_angles`, `corner_condition_error`, `corner_line_count`, `required_corner_lines`, `corner_score`.
- Added evaluation module:
  - `src/engine/creasegen_evaluation.ts`
  - ported `vertex_kawasaki_error`, `kawasaki_score`, `priority_corner_kawasaki_score`, `global_score`.
- Integrated metrics into runtime:
  - `src/engine/creasegen.ts`
  - `runCreasegen(...).metrics` now uses calculated values instead of placeholders.
- Added/updated exports and fixtures:
  - `src/engine/index.ts`
  - `src/engine/creasegen_fixtures.ts` (metrics assertions)

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners:
  - `metrics`: `cornerViolationsAfter=5`, `kawasakiViolationsAfter=2`, `priorityCornerKawasakiViolationsAfter=0`
  - `graph.stats`: `vertexCount=14`, `edgeCount=27`, `boundaryEdgeCount=4`, `cornerCount=9`

## 21. Stage B Greedy Search Step (Pre-DFS)
- Added ray action module:
  - `src/engine/creasegen_actions.ts`
  - includes `applyRayAction(...)` with symmetry-consistency check.
- Added lightweight search module:
  - `src/engine/creasegen_search.ts`
  - includes admissible-dir filtering, candidate ranking, and `runGreedyRepair(...)`.
- Runtime integration:
  - `src/engine/creasegen.ts`
  - now runs `runGreedyRepair(...)` after seeding (bounded by `maxDepth` / `maxNodes`).
- Export updates:
  - `src/engine/index.ts`
- Fixture enhancement:
  - `src/engine/creasegen_fixtures.ts`
  - verifies greedy stats are populated.

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners:
  - `metrics`: unchanged at `cornerViolationsAfter=5`, `kawasakiViolationsAfter=2`, `priorityCornerKawasakiViolationsAfter=0`
  - `search_stats`: includes `greedy_depth_round`, `greedy_node_eval`, `candidate_dirs_total` (greedy step executed)

Status:
- Stage B now has seed graph + scoring + one-step greedy improvement in Worker runtime.
- Remaining for parity: full DFS (`search.py`) + staged search + prune pipeline.

## 22. Stage B DFS Core Port (No Open-Sink Yet)
- Added search policy module:
  - `src/engine/creasegen_search_policy.ts`
  - includes `solvedByScore`, `pruneReason`, `scoreRejectReason`, `childSortKey`.
- Extended search module:
  - `src/engine/creasegen_search.ts`
  - added `runDfsRepair(...)` with:
    - state-key dedup,
    - score/priority caches,
    - branch/depth/node pruning,
    - move-equivalence dedup,
    - candidate ranking and child sort policy.
- Runtime integration:
  - `src/engine/creasegen.ts`
  - `runCreasegen(...)` now executes:
    1) seed graph
    2) greedy repair
    3) DFS repair (ray action only)
- Export updates:
  - `src/engine/index.ts`
- Fixture updates:
  - `src/engine/creasegen_fixtures.ts`
  - now asserts DFS stats presence (`recurse_calls`).

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners:
  - `metrics`: `cornerViolationsAfter=5`, `kawasakiViolationsAfter=2`, `priorityCornerKawasakiViolationsAfter=0`
  - `graph.stats`: `vertexCount=21`, `edgeCount=46`, `boundaryEdgeCount=4`, `cornerCount=9`
  - `search_stats`: includes DFS counters (`recurse_calls=311`, `visited_nodes=311`, `accepted_children=548`, `prune_max_depth=222`)

Status:
- Stage B search now includes DFS branch exploration with ray actions.
- Remaining parity gap: open-sink actions, corner-kawasaki repair hooks, staged-k relax/refresh/final-prune pipeline.

## 23. Stage B Open-Sink Action Port (Core)
- Extended action module:
  - `src/engine/creasegen_actions.ts`
  - added:
    - `runOpenSinkTransaction(...)`
    - `applyOpenSinkAction(...)`
    - `repairOpenSinkVertices(...)`
    - `repairPriorityCornersOpenSink(...)`
    - `applyCandidateAction(...)`
- DFS integration:
  - `src/engine/creasegen_search.ts`
  - `runDfsRepair(...)` now uses `applyCandidateAction(...)` and therefore honors:
    - `enableOpenSink`
    - `enableOpenSinkRepair`
    - `enableCornerKawasakiRepair`
- Behavior:
  - search can now branch with open-sink style propagation and optional repair hooks.

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners (open-sink enabled):
  - `metrics`: `cornerViolationsAfter=2`, `kawasakiViolationsAfter=2`, `priorityCornerKawasakiViolationsAfter=0`
  - `graph.stats`: `vertexCount=23`, `edgeCount=48`, `boundaryEdgeCount=6`, `cornerCount=9`
  - `search_stats`: includes open-sink attempts and reject counters (`reject_action_failed`, `reject_missing_grid_point`, etc.)

Status:
- Stage B now has seed + greedy + DFS + open-sink core action path in Worker runtime.
- Remaining parity gap centers on staged search orchestration and prune/refresh passes.

## 24. Stage B Staged-K Relax Orchestration (Initial)
- Updated `runCreasegen(...)` orchestration in:
  - `src/engine/creasegen.ts`
- Added initial staged loop behavior:
  - honors `stagedKRelax` and `kStart`.
  - runs stage sequence `kStartEffective ... kMaxEffective`.
  - remaps intermediate best graph into refined grid via `remapGraphToNewGrid(...)`.
  - records per-stage log entries in `graph.stageLogs`.
- Parameter surface update in emitted graph:
  - `params.kStartEffective`
  - `params.kEffective`
- Fixture enhancement:
  - `src/engine/creasegen_fixtures.ts`
  - verifies staged run emits multi-stage logs and expected effective-k params.

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; runQsqrt2Fixture(); import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; runTilingFixture(); import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; runFoldPreviewFixture(); import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Staged smoke on `_tmp_out/cp_graph_test2.json` corners:
  - `metrics`: `cornerViolationsAfter=2`, `kawasakiViolationsAfter=2`, `priorityCornerKawasakiViolationsAfter=0`
  - `graph.stats`: `vertexCount=30`, `edgeCount=61`, `boundaryEdgeCount=8`, `cornerCount=9`
  - `params`: `kStartEffective=1`, `kEffective=2`
  - `stageLogs`: `2`

Status:
- Stage B runtime now includes an initial staged-k relaxation pipeline.
- Remaining parity gap: auto-expand planning and prune/refresh/final-prune stages.

## 25. Stage B Auto-Expand Loop (Initial, Coarse)
- Added expand utilities:
  - `src/engine/creasegen_expand.ts`
  - `expandRequestFromStats(...)`
  - `mergeSearchStats(...)`
  - `effectiveStallRounds(...)` (initial simple policy)
- Updated `runCreasegen(...)`:
  - `src/engine/creasegen.ts`
  - seed phase now supports `seedAutoExpand` / `seedAutoExpandMaxRounds`.
  - stage phase now supports coarse `autoExpandGrid` loop with stall detection.
  - on expansion trigger, rebuilds grid with larger `(aMax, bMax)` and remaps current graph.
  - logs seed/auto-expand events into `stageLogs`.
- Safety guard:
  - provisional work bound cap `MAX_WORK_BOUND=12` to prevent runaway lattice growth during early migration stage.

Validation on 2026-02-20:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Auto-expand smoke on `_tmp_out/cp_graph_test2.json` corners (light settings):
  - `metrics`: `cornerViolationsAfter=5`, `kawasakiViolationsAfter=8`, `priorityCornerKawasakiViolationsAfter=0`
  - `graph.stats`: `vertexCount=71`, `edgeCount=144`, `boundaryEdgeCount=8`, `cornerCount=9`
  - `stageLogs`: `3`

Status:
- Stage B now includes initial auto-expand execution flow.
- Remaining parity gap: need detection/planning parity with Python (`stage_expand_planning`), plus refresh/final-prune integration.

## 26. Stage B Auto-Expand Planning Parity (Detect/Plan/Apply)
- Extended expand module:
  - `src/engine/creasegen_expand.ts`
  - added Python-parity utilities and planning flow:
    - `requiredNormBoundsFromGridBounds(...)`
    - `detectExpandNeed(...)`
    - `planExpandTarget(...)`
    - `expandMode(...)`
    - growth probes and corner-required expansion analyzers
    - `usedDirIndices(...)` (for forced expand seed move checks)
- Updated Stage B orchestration:
  - `src/engine/creasegen.ts`
  - seed auto-expand now tracks and updates:
    - `a_work`, `b_work`, `a_norm_work`, `b_norm_work`, `k_start_effective`
  - coarse stage loop now follows Python-style pipeline:
    1) stall detect
    2) expand need detect (`round_missing_grid` / `grid_required_corner`)
    3) target planning (`planExpandTarget`)
    4) expand apply + optional forced seed ray on representative corner
  - emits richer stage logs:
    - `reason`, `mode`, `required_corner_*`, `a_max/b_max/a_norm/b_norm/k_max`
  - graph params now correctly store:
    - `seedExpandRoundsUsed`

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runQsqrt2Fixture(); runTilingFixture(); runFoldPreviewFixture(); runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners (staged + auto-expand enabled):
  - `metrics`:
    - `cornerViolationsAfter=0`
    - `kawasakiViolationsAfter=0`
    - `priorityCornerKawasakiViolationsAfter=0`
  - `params`:
    - `kStartEffective=1`
    - `kEffective=2`
    - `seedExpandRoundsUsed=1`
  - `search_stats` include:
    - `round_missing_grid_expand_detect`
    - `round_missing_grid_corner_count_max`
    - `auto_expand_with_ab`
    - `auto_expand_seed_*` family (attempt/fail/success/reject)

Status:
- Stage B auto-expand now uses Python-equivalent detect/plan/apply semantics.
- Remaining parity gap: refresh/final-prune/draft-guided integration and full tuning of branch heuristics.

## 27. Stage B Final-Prune Integration (Initial)
- Added prune-axis module:
  - `src/engine/creasegen_prune_axes.ts`
  - includes:
    - line-key extraction on 16-dir lattice
    - axis-cycle candidate collection (`collectAxisCycleTargets`)
    - delete-group transaction with symmetry/Kawasaki guards
    - `refreshGraphByPruning(...)`
- Added final-prune rounds module:
  - `src/engine/creasegen_final_prune.ts`
  - includes `applyFinalPruneRounds(...)` with Python-aligned acceptance checks:
    - global Kawasaki non-worse
    - corner score non-worse
    - preserve-satisfied-corners
    - priority-corner Kawasaki non-worse
- Runtime integration:
  - `src/engine/creasegen.ts`
  - `runCreasegen(...)` now executes final prune when:
    - `finalPrune=true`
    - `finalPruneRounds>0`
    - `finalPruneMaxCandidates>0`
  - final budget params emitted in cp graph memory:
    - `aMaxEffective`, `bMaxEffective`, `aNormEffective`, `bNormEffective`
- Export updates:
  - `src/engine/index.ts`

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runQsqrt2Fixture(); runTilingFixture(); runFoldPreviewFixture(); runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners (auto-expand + final-prune on):
  - metrics remain solved:
    - `cornerViolationsAfter=0`
    - `kawasakiViolationsAfter=0`
    - `priorityCornerKawasakiViolationsAfter=0`
  - final budget params:
    - `aMaxEffective=12`
    - `bMaxEffective=12`
    - `aNormEffective=3`
    - `bNormEffective=4`
    - `kStartEffective=1`
    - `kEffective=2`
  - prune stats are populated (`prune_tx_attempted_total` etc.); this fixture had no accepted final-prune round (`finalPruneLogs=0`).

Status:
- Stage B now has end-stage prune hooks in TS runtime.
- Remaining parity gap: draft-guided path and deeper heuristic tuning for prune acceptance on broader fixtures.

## 28. Stage B Draft-Guided Search Hints (Initial)
- Extended DFS search interface:
  - `src/engine/creasegen_search.ts`
  - added optional preferred-direction hints:
    - `PreferredDirHints` type
    - `runDfsRepair(..., preferredDirHints?)`
  - `collectTrialDirs(...)` now supports preferred dirs and records hint stats:
    - `hint_preferred_vertex`
    - `hint_preferred_dir_used`
- Added draft-guided orchestration in Stage B runtime:
  - `src/engine/creasegen.ts`
  - when `draftGuided=true`:
    1. run a reduced-budget draft search (bounded by `draftMaxDepth`, `draftBranchPerNode`, `draftMaxNodes`)
    2. extract hint dirs from draft-vs-base corner direction deltas
    3. apply forced hint rays at search start
    4. pass hints into DFS rounds
  - emits draft-related stage logs:
    - `draft_guided`
    - `draft_hint_force_start`
  - records draft hint counters in `searchStats`:
    - `draft_hint_corner_count`
    - `draft_hint_dir_total`
    - `draft_hint_forced_*`
- Fixture update:
  - `src/engine/creasegen_fixtures.ts`
  - added `draftGuided=true` check for stage-log and stats presence.

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runQsqrt2Fixture(); runTilingFixture(); runFoldPreviewFixture(); runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners with `draftGuided=true`:
  - `metrics` remained solved:
    - `cornerViolationsAfter=0`
    - `kawasakiViolationsAfter=0`
    - `priorityCornerKawasakiViolationsAfter=0`
  - draft logs present:
    - `hasDraftLog=true`
    - `hasDraftForceLog=true`
  - draft stats sample:
    - `draft_hint_corner_count=1`
    - `draft_hint_dir_total=2`
    - `draft_hint_forced_attempt=2`
    - `draft_hint_forced_applied=1`

Status:
- Stage B now includes initial draft-guided hint generation and consumption path.
- Remaining parity gap: draft hint extraction heuristic is currently delta-based (not full Python scoring-based extraction), and prune acceptance tuning remains.

Update on 2026-02-21 (parity refinement):
- Replaced delta-based hint extraction with Python-aligned scoring-based selection:
  - per-corner `before_err`, `deficit`, admissible/unused/feasible direction scan
  - `corner_condition_error_with_added_dir` gain ranking
  - selected count = `min(len(candidates), max(1, deficit))`
- Added safety rollback for forced hint pre-application:
  - if forced-start graph is worse than pre-force graph (global score or priority-corner Kawasaki), revert to pre-force graph.
  - keeps draft hints active for DFS ordering even when forced start is reverted.

Validation on 2026-02-21:
- `_tmp_out/cp_graph_test2.json` corners:
  - `draftGuided=false`: `corner=2`, `kawasaki=2`
  - `draftGuided=true`: `corner=2`, `kawasaki=2` (no degradation after rollback guard)
  - `searchStats.draft_hint_forced_reverted_worse=1`

## 29. Stage B DFS Refresh-Pruning Hook (Parity)
- Extended DFS search loop:
  - `src/engine/creasegen_search.ts`
  - added periodic refresh hook (Python `search.py` parity):
    - every fixed node interval (`refreshEveryNodes=30`)
    - invoke `refreshGraphByPruning(...)`
    - accept only when refresh is non-worse by score policy (`refreshAcceptable`)
    - preserve state dedup constraints (`refresh_reject_seen`)
  - added refresh counters in `searchStats`:
    - `refresh_trigger`
    - `refresh_applied`
    - `refresh_removed_edges`
    - `refresh_reject_seen`
    - `refresh_reject_worse`
    - `refresh_nochange`
- Search policy update:
  - `src/engine/creasegen_search_policy.ts`
  - added `refreshAcceptable(...)`.
- Prune parity refinements:
  - `src/engine/creasegen_prune_axes.ts`
  - `edgeDirFrom(...)` now includes direction fallback (not bucket-only)
  - local Kawasaki boundary check now uses `isBoundaryVertex(...)`
  - delete-group processing order made numeric (Python tuple-order aligned)

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`
- Regression fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runQsqrt2Fixture } from './src/engine/qsqrt2_fixtures.ts'; import { runTilingFixture } from './src/engine/tiling_fixtures.ts'; import { runFoldPreviewFixture } from './src/engine/fold_preview_fixtures.ts'; import { runCreasegenGraphFixture } from './src/engine/creasegen_graph_fixtures.ts'; runQsqrt2Fixture(); runTilingFixture(); runFoldPreviewFixture(); runCreasegenGraphFixture(); console.log('REGRESSION_FIXTURES_OK');"`
- Smoke on `_tmp_out/cp_graph_test2.json` corners:
  - metrics unchanged (no regressions):
    - `cornerViolationsAfter=2`
    - `kawasakiViolationsAfter=2`
    - `priorityCornerKawasakiViolationsAfter=0`
  - refresh instrumentation active:
    - `refresh_trigger` observed (`3-4` in tested configs)
    - this fixture had no accepted refresh (`refresh_applied=0`).

## 30. Real-Data Evaluation Profiles (Prune Tuning Deferred)
- Added evaluation utility for running multiple `runCreasegen` profiles on the same corner set:
  - `src/engine/creasegen_profiles.ts`
  - exports:
    - `evaluateCreasegenProfiles(...)`
    - `summarizeCreasegenResult(...)`
    - `compareCreasegenSummaries(...)`
- Added default real-data profile set:
  - `baseline_no_prune` (recommended first pass)
  - `draft_guided_no_prune`
  - `full_with_prune` (reference only)
- Added fixture:
  - `src/engine/creasegen_profiles_fixtures.ts`
  - verifies:
    - profile execution pipeline works
    - baseline profile keeps `finalPrune=false`
    - summary/comparator contracts are stable

Policy update:
- `prune` heuristic tuning is intentionally deferred until real-data test phase.
- Until then, use `baseline_no_prune` as the default profile for parity/diagnostic runs, and treat `full_with_prune` as comparison-only.

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- New fixture:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenProfilesFixture } from './src/engine/creasegen_profiles_fixtures.ts'; runCreasegenProfilesFixture(); console.log('CREASEGEN_PROFILES_FIXTURE_OK');"`

## 31. Worker Protocol: Profile Evaluation Command
- Extended worker protocol:
  - `src/engine/worker_protocol.ts`
  - added command:
    - `runCreasegenProfiles`
  - request payload:
    - `RunCreasegenProfilesInput`
  - result payload:
    - `{ evaluations, best, bestResult }`
- Extended worker client:
  - `src/engine/client.ts`
  - added:
    - `runCreasegenProfiles(...)`
- Extended worker runtime:
  - `src/workers/origami_engine.worker.ts`
  - added:
    - profile evaluation branch with progress events (`profile eval start/done`)
    - per-profile progress messages (`profile i/n: <name>`)
    - cancel check between profiles
    - best-profile selection by `pickBestCreasegenEvaluation(...)`
- Extended profile utility API:
  - `src/engine/creasegen_profiles.ts`
  - added:
    - `resolveCreasegenEvalProfiles(...)`
    - `evaluateCreasegenProfile(...)`
    - `pickBestCreasegenEvaluation(...)`
    - `evaluateCreasegenProfilesWithBest(...)`

Validation on 2026-02-21:
- Type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenProfilesFixture } from './src/engine/creasegen_profiles_fixtures.ts'; runCreasegenProfilesFixture(); console.log('CREASEGEN_PROFILES_FIXTURE_OK');"`
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`

## 32. Repository Layout Separation (Python vs Web App)
- Moved Web app related files under:
  - `webapp/src/**`
  - `webapp/docs/**`
  - `webapp/tsconfig.json`
- Python code remains under:
  - `py/**`

Operational note:
- Run all TypeScript checks and fixtures from `webapp/` as working directory.

## 33. Vue + Vite Bootstrap (Initial)
- Added web app runtime scaffold:
  - `webapp/package.json`
  - `webapp/index.html`
  - `webapp/vite.config.ts`
  - `webapp/tsconfig.web.json`
  - `webapp/README.md`
- Added Vue UI entry:
  - `webapp/ui/main.ts`
  - `webapp/ui/App.vue`
  - `webapp/ui/styles.css`
  - `webapp/ui/vite-env.d.ts`
- Connected UI to worker command:
  - uses `WorkerOrigamiEngine.runCreasegenProfiles(...)`
  - supports:
    - sample-corner run
    - preset cp_graph sample load (`public/samples/*.json`)
    - cp_graph_v1 JSON import
    - profile comparison table + best-profile highlight + search-stat columns
    - progress/status display from worker events

Validation on 2026-02-21:
- Engine type check:
  - `npm exec --yes --package typescript tsc -- --noEmit -p tsconfig.json`
- Fixtures:
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenProfilesFixture } from './src/engine/creasegen_profiles_fixtures.ts'; runCreasegenProfilesFixture(); console.log('CREASEGEN_PROFILES_FIXTURE_OK');"`
  - `npm exec --yes --package tsx -- tsx --eval "import { runCreasegenFixture } from './src/engine/creasegen_fixtures.ts'; runCreasegenFixture(); console.log('CREASEGEN_FIXTURE_OK');"`

## 34. Vue Runtime Verification (Installed + Build Passed)
- Installed web app dependencies in `webapp/`:
  - `npm install`
  - lockfile generated: `webapp/package-lock.json`
- Added web app ignore rules:
  - `webapp/.gitignore` (`node_modules/`, `dist/`)
- Verified Vue typecheck and production build:
  - `npm run typecheck:web`
  - `npm run build`
- Build output includes worker bundle:
  - `dist/assets/origami_engine.worker-*.js`

## 35. Corner Designer UI (Symmetry-Aware)
- Upgraded `webapp/ui/App.vue` to include `Corner Designer`:
  - direct point placement on unit-square canvas (click to add, drag to move)
  - symmetry toggle (`y = x`)
  - symmetry-on placement modes:
    - `axis` points
    - `side` points (one-side input with mirrored rendering)
  - editable grid controls:
    - run config `a,b,k`
    - corner snap density `snap k`
  - selected-point inspector:
    - coordinate edit
    - visual size edit
    - delete selected
  - source mode switch:
    - `designer`
    - `external` (preset/imported cp_graph)
- Updated result table to keep prune diagnostics visible:
  - `recurse`
  - `refresh applied/trigger`
  - `final prune rounds/removed edges`
- Styling updates in `webapp/ui/styles.css` for designer canvas and controls.

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 43. UX Follow-Up: Restore Axis/Side Visuals + Direct Corner Canvas Editing
- Restored tiling-point canvas styling and semantics:
  - axis/side/free color coding restored
  - side mirrored-visual points restored on opposite side of `y=x`
- Added separate creasegen-corner editing canvas:
  - click to add corners directly for run input
  - drag to move selected corner
  - optional faint snapped-grid point overlay
  - independent source selection (`Use This Corner Layout`)
- Active run-corner source and list remain explicit in `Run & Data` panel.

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 42. UX Clarification: Language + Canvas Role Split
- Added UI language selector (`日本語` / `English`) in `webapp/ui/App.vue`.
- Clarified creasegen corner source:
  - added `Corners Used For Creasegen` box showing current source and active corner list.
- Simplified point rendering in corner layout canvas:
  - unified editable points to a single marker style.
  - removed mixed marker layers from corner designer view.
- Split visual roles of canvases:
  - `Corner Layout Canvas`: edit corners for creasegen input.
  - `Tiling Stage` canvas: visualize tiling centers only.

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 41. Folded Preview Integration in UI
- Added `Folded Preview` panel in `webapp/ui/App.vue`:
  - runs worker `runPreview` against currently selected profile graph
  - auto-runs preview for best profile after profile-comparison run
  - includes preview controls:
    - `alpha`
    - `line width`
    - `face id` toggle
- Added SVG folded-face rendering:
  - fits reconstructed face polygons to viewport
  - colors faces as semi-transparent layered surfaces by depth ordering
  - optional face-id labels
  - stats display (`segment/face/dual edge/inconsistency`)

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 40. Crease Pattern Visualization in UI
- Added `Crease Pattern View` panel in `webapp/ui/App.vue`:
  - renders generated `CreaseGraphMem` as SVG
  - internal/boundary edges with separate styles
  - corner/boundary/internal vertex markers
  - graph stats summary (`vertex/edge/boundary edge/corner`)
- Added profile-linked preview selection:
  - preview defaults to best profile after run
  - clicking evaluation rows switches preview target profile

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 39. Arbitrary Grid Seed Segments (Exact Endpoints)
- Added optional exact segment contract:
  - `CreaseBuildInput.seedSegments`
  - `RunCreasegenProfilesInput.seedSegments`
- Propagated through profile/worker path:
  - `evaluateCreasegenProfile(s)` forwards `seedSegments` to `runCreasegen(...)`
  - worker `runCreasegenProfiles` forwards payload `seedSegments`
- Grid construction update:
  - `makeGridGraph(...)` now accepts `initialSegments`
  - each segment endpoint is resolved as a grid point via `addVertex(...)`
  - segment path insertion uses `addSegmentWithSplitsIds(...)`
  - stats added:
    - `initial_seed_segment_attempt`
    - `initial_seed_segment_applied`
    - `initial_seed_segment_failed`
    - `initial_seed_segment_invalid`
    - `initial_seed_segment_missing_point`
- Bounds handling:
  - `runCreasegen(...)` now includes `seedSegments` endpoints in effective bound calculation
- UI update (`webapp/ui/App.vue`):
  - added `Grid Seed Segments (Exact)` editor with `(a,b,k)` inputs for from/to x,y
  - supports symmetry auto-mirror (`y=x`) at run-time payload expansion

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 38. Seed-Edge Symmetry Auto-Mirroring (UI)
- Extended seed-edge UI behavior in `webapp/ui/App.vue`:
  - added `auto mirror by y=x` toggle for symmetry workflows
  - computes run-time seed edge list as:
    - user-entered seed edges
    - plus mirrored pairs when symmetry mode + auto-mirror are enabled
  - deduplicates normalized pairs and skips invalid/self pairs
- Run payload update:
  - `runCreasegenProfiles` now sends expanded run-time seed edge list (`seedEdgesForRun`)

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 37. Initial Seed-Edge Path (UI -> Worker -> Creasegen)
- Added optional seed-edge input contract:
  - `CreaseBuildInput.seedEdges`
  - `RunCreasegenProfilesInput.seedEdges`
- Extended grid graph construction:
  - `makeGridGraph(...)` accepts `initialCornerEdgePairs`
  - initial corner-pair segments are added before direct-corner seeding
  - seed-edge counters added to seed stats:
    - `initial_seed_edge_attempt`
    - `initial_seed_edge_applied`
    - `initial_seed_edge_failed`
    - `initial_seed_edge_invalid`
- Propagated seed edges through profile execution path:
  - `evaluateCreasegenProfile(s)` now forward `seedEdges` into `runCreasegen(...)`
  - worker `runCreasegenProfiles` forwards payload seed edges
- Added seed-edge editor in UI (`webapp/ui/App.vue`):
  - choose `corner i` and `corner j` from current active corners
  - add/remove/clear seed edges
  - optional list is sent with `Run Profile Comparison`

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`

## 36. Tiling Stage Wiring from Corner Designer
- Extended `webapp/ui/App.vue` with a dedicated `Tiling Stage` panel:
  - build `TilingRunInput` from designer groups (`axis` + `side`)
  - editable tiling knobs:
    - `seed`
    - `den candidates`
    - `coeff candidates`
    - `alpha steps`
    - `pack restarts`
    - `pack iters`
  - actions:
    - `Run Tiling From Designer`
    - `Use Tiling Centers As Corners`
- Added visual feedback:
  - tiling centers rendered as blue markers on designer canvas
  - tiling summary line (`ok`, `alpha`, `den`, `coeff`, `cornerHits`, `contact`)
- `runCreasegenProfiles` now receives optional tiling object when available.

Validation on 2026-02-21:
- `npm run typecheck:web`
- `npm run typecheck:engine`
- `npm run build`
