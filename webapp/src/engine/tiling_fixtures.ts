import { runTiling } from "./tiling";
import type { KadoSpec, TilingRunInput } from "./types";

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

function specsTwoAxis(): KadoSpec[] {
  return [
    { name: "A0", length: 1.0, symmetry: "axis" },
    { name: "A1", length: 1.0, symmetry: "axis" },
  ];
}

export function runTilingFixture(): void {
  const input: TilingRunInput = {
    specs: specsTwoAxis(),
    lattice: { aMax: 2, bMax: 2, kMax: 2 },
    seed: 0,
    alphaSteps: 6,
    packRestarts: 4,
    packIters: 120,
    packGuidedRestarts: 2,
    packGuidedJitter: 0.08,
    warmStart: true,
  };

  const out1 = runTiling(input);
  const out2 = runTiling(input);

  assert(out1.ok, "tiling should be feasible for two-axis fixture");
  assert(Object.keys(out1.centers).length === 2, "center count mismatch");
  assert(out1.alpha > 0, "alpha should be positive");
  assert(out1.alpha === out2.alpha, "determinism mismatch: alpha");
  assert(
    JSON.stringify(out1.centers) === JSON.stringify(out2.centers),
    "determinism mismatch: centers",
  );
}
