# cp_graph Policy Test Checklist

Goal:
- Verify import/export behavior for `cp_graph_v1` under centered-world migration.

Preconditions:
- Web app builds successfully.
- Use at least one generated graph (`Run crease generation`) and one legacy sample (`public/samples/*.json`).

## A. Import Policy

1. Auto + legacy sample (`domain=[0,1]`)
- Set `Import policy = auto`.
- Load preset `cp_graph_test2`.
- Confirm source label includes legacy conversion.
- Confirm corners appear within current paper window.

2. Forced legacy
- Set `Import policy = legacy [0,1]`.
- Load same preset.
- Confirm behavior matches case A-1 regardless of domain metadata.

3. Forced centered/world
- Set `Import policy = centered/world`.
- Load same preset.
- Confirm no legacy shift is applied.
- Confirm source label indicates centered/world as-is.

4. Non-zero originOffset import
- Set originOffset to non-zero dyadic.
- Repeat A-1 and A-2.
- Confirm imported corners translate with originOffset as expected.

## B. Export Policy

1. Export centered/world
- Generate a graph and open CP view.
- Set `Export mode = centered/world`.
- Export JSON.
- Open exported file and confirm `domain` equals current paper window bounds.

2. Export legacy [0,1]
- Set `Export mode = legacy [0,1]`.
- Export JSON.
- Open file and confirm domain is `[0,1] x [0,1]`.
- Confirm approximate points are shifted to legacy frame.

3. Roundtrip centered
- Import centered export with `Import policy = centered/world`.
- Confirm corner placement matches original world layout.

4. Roundtrip legacy
- Import legacy export with `Import policy = auto` and then forced `legacy`.
- Confirm corners map back to expected world frame using current originOffset.

## C. Symmetry Consistency

1. Local symmetry mirror
- With non-zero originOffset and symmetry enabled, place side points.
- Confirm mirrored preview points are reflected around local `y=x` axis.

2. Seed auto-mirror
- Add seed edge/segment with auto-mirror enabled.
- Confirm generated mirrored entities follow local symmetry, not raw world `x<->y`.

